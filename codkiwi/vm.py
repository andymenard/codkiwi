"""Pure Python Kiwi interpreter, derived from the CoD ARMv7/JS reconstruction.

No RenPy dependency. 16-bit cells, retained stack backing, and explicit waits.
See docs/NATIVE_VM_README.md for fidelity limits and evidence provenance.
"""
import copy
import struct


def signed(n):
    n = int(n) & 65535
    return n - 65536 if n & 32768 else n


# Scripts were authored in Unicode and stored one byte per character, so every
# codepoint was truncated to its low byte. Anything in General Punctuation
# (U+2000-U+20FF) therefore landed in 0x00-0xFF, and the ones that landed below
# 0x20 survive as control codes no encoding can render: a typographic apostrophe
# (U+2019 & 255 = 0x19) shows up as a box mid-word, which is where "I'll pull the
# car around" lost its apostrophe. Two bytes actually occur across the
# 103-container corpus - 0x09 for U+2009 THIN SPACE and 0x19 for U+2019 - but the
# whole range is mapped because the cause is the same for all of them.
#
# The space variants become an ordinary space and the invisible formatting marks
# are dropped: the game's fonts carry the punctuation but none of those, so
# restoring them literally would trade one empty box for another.
GENERAL_PUNCTUATION = ([''] + [' '] * 10 + [''] * 5
                       + [chr(0x2000 + code) for code in range(0x10, 0x20)])


def has_operand(raw):
    return raw in (1, 0x40, 0x41, 0x5c) or (0x19 <= raw <= 0x2e and bool(0x003f84e7 & (1 << (raw - 0x19))))


def parse_kiwi(data):
    if len(data) < 15 or data[:4] != b'kiwi':
        raise ValueError('Not a Kiwi script')
    cursor = 4
    version = data[cursor]; cursor += 1
    library = False; split = 0x8000; library_limit = None
    def short():
        nonlocal cursor
        value = struct.unpack_from('>H', data, cursor)[0]; cursor += 2
        return value
    if version > 1:
        library = bool(data[cursor]); cursor += 1
        if library:
            split, library_limit = short(), short()
    external = data[cursor]; cursor += 1
    primary, secondary, tertiary, count = short(), short(), short(), short()
    cells = [short() for _ in range(primary)] + [0] * secondary + [short() for _ in range(tertiary)]
    instructions = []
    for index in range(count):
        raw = data[cursor]; cursor += 1
        operand = short() if has_operand(raw) else None
        instructions.append({'index': index, 'raw': raw, 'operand': operand})
    if cursor != len(data):
        raise ValueError('Trailing Kiwi bytes: %s' % (len(data) - cursor))
    return dict(version=version, cells=cells, instructions=instructions,
                hasLibraryData=library, dataSplitAddress=split, libraryDataLimit=library_limit,
                externalInstructionSet=external)


class KiwiVM:
    NOOPS = {2,6,9,16,20,29,39,47,48,49,52,53,54,55,56,57,58,59,60,61,68,69,71,73,75,76,77,78,79,85,86,87,88,89,93,94}

    def __init__(self, program, host=None):
        if program.get('hasLibraryData') or program.get('externalInstructionSet'):
            raise NotImplementedError('Optional Kiwi library/external instruction set is not verified')
        # Only `cells` is written to - the data segment is self-modifying.
        # The instruction stream is read-only (step() reads ins['raw'] and
        # ins['operand'] and nothing assigns to either), so it is shared with
        # the parsed program rather than deep-copied on every script load.
        self.program = dict(program, cells=list(program['cells']))
        self.host = host
        self.ip = self.sp = self.bp = self.pri = self.alt = self.sys = self.steps = 0
        self.stack = [None] * 1024
        self.stackAddress = program.get('stackAddress', 0x7bf5)
        self.dataSplitAddress = program.get('dataSplitAddress', 0x8000)
        self.pendingSyscall = None
        self.stringSlots = []
        self.state = 'ready'

    def push(self, value):
        if not 0 <= self.sp < 1024:
            raise RuntimeError('Kiwi stack overflow')
        if not isinstance(value, int):
            raise RuntimeError('Uninitialized value pushed onto stack')
        self.stack[self.sp] = value & 65535; self.sp += 1

    def peek(self):
        if self.sp < 1:
            raise RuntimeError('Stack underflow at instruction %s' % self.ip)
        value = self.stack[self.sp - 1]
        if value is None:
            raise RuntimeError('Uninitialized stack read')
        return value

    def pop(self):
        value = self.peek(); self.sp -= 1
        return value

    def region(self, pointer):
        address = signed(pointer)
        if address < 0:
            raise RuntimeError('Negative memory pointer %s' % address)
        if address >= self.stackAddress:
            return self.stack, address - self.stackAddress
        return self.program['cells'], address

    def read(self, pointer):
        cells, index = self.region(pointer)
        if index >= len(cells) or cells[index] is None:
            raise RuntimeError('Invalid/uninitialized Kiwi read at %s' % pointer)
        return cells[index]

    def write(self, pointer, value):
        cells, index = self.region(pointer)
        if index >= len(cells):
            raise RuntimeError('Invalid Kiwi write at %s' % pointer)
        cells[index] = value & 65535

    def read_string(self, pointer):
        if signed(pointer) == -1:
            return ''
        data = bytearray()
        for offset in range(0x8000):
            cell = self.read(pointer + offset)
            if not cell >> 8: break
            data.append(cell >> 8)
            if not cell & 255: break
            data.append(cell & 255)
        # WHATWG windows-1252 preserves undefined control-code positions.
        return ''.join(GENERAL_PUNCTUATION[v] if v < 32 else
                       bytes([v]).decode('cp1252') if v not in (129,141,143,144,157) else chr(v)
                       for v in data)

    def write_string(self, pointer, text):
        data = [ord(c) & 255 for c in text] + [0]
        for index in range(0, len(data), 2):
            self.write(pointer + index // 2, (data[index] << 8) | (data[index+1] if index+1 < len(data) else 0))

    def slot(self, index, value):
        if not 0 <= index <= 10:
            raise RuntimeError('Invalid host string slot %s' % index)
        self.stringSlots.extend([None] * max(0, index + 1 - len(self.stringSlots)))
        self.stringSlots[index] = value
        return 0x7ff5 + index

    def call(self, ident, argc):
        if not 0 <= argc <= self.sp:
            raise RuntimeError('Syscall %s requests %s arguments from %s cells' % (ident, argc, self.sp))
        args = self.stack[self.sp - argc:self.sp]
        self.pendingSyscall = {'id': ident, 'argc': argc}
        result = self.host(ident, args, self) if self.host else 0
        if isinstance(result, dict) and result.get('wait'):
            self.state = 'waiting'
        else:
            self.resume(result if isinstance(result, int) else 0)

    def resume(self, result=0):
        if self.pendingSyscall is None:
            raise RuntimeError('No pending syscall')
        self.sp -= self.pendingSyscall['argc']
        self.sys = result & 65535
        self.pendingSyscall = None; self.state = 'running'

    def execute(self, limit=100000):
        if self.pendingSyscall:
            raise RuntimeError('Cannot execute a pending syscall')
        self.state = 'running'
        stop = self.steps + limit
        while self.state == 'running' and self.steps < stop:
            self.step()
        if self.state == 'running': self.state = 'paused'
        return self.state

    def step(self):
        if not 0 <= self.ip < len(self.program['instructions']):
            raise RuntimeError('Invalid instruction pointer %s' % self.ip)
        ins = self.program['instructions'][self.ip]
        r, o = ins['raw'], ins['operand']
        self.ip += 1; self.steps += 1
        def jump(): self._relative(o)
        if r == 1: self.pri = o
        elif r == 3: self.pri = self.pop()
        elif r == 4: self.alt = self.pop()
        elif r == 5: self.pri = self.peek()
        elif r == 7: self.push(self.pri)
        elif r == 8: self.push(self.alt)
        elif r in (10,11,12,13,14,15,17,18,80,81,82,83,84):
            b, a = self.pop(), self.pop()
            if r == 10: value = int(a == b)
            elif r == 11: value = int(a != b)
            elif r == 12: value = int(signed(b) < signed(a))
            elif r == 13: value = int(signed(b) <= signed(a))
            elif r == 14: value = int(signed(b) > signed(a))
            elif r == 15: value = int(signed(b) >= signed(a))
            elif r == 17: value = int(bool(a or b))
            elif r == 18: value = int(bool(a and b))
            elif r == 80: value = a + b
            elif r == 81: value = a - b
            elif r == 82: value = a * b
            else:
                if not b: raise RuntimeError('Undefined native division by zero')
                quotient = abs(signed(a)) // abs(signed(b))
                if (signed(a) < 0) != (signed(b) < 0): quotient = -quotient
                value = quotient if r == 83 else signed(a) - quotient * signed(b)
            self.push(value)
        elif r == 19: self.push(int(not self.pop()))
        elif 21 <= r <= 25:
            for _ in range(o if r == 25 else r - 20): self.pop()
        elif r == 26: self.push(o)
        elif r == 27:
            self.push((o & 255) - (256 if o & 128 else 0))
            self.push((o >> 8) - (256 if o & 32768 else 0))
        elif r == 28: self.push(self.peek())
        elif r == 30: self.call(o, self.sys)
        elif r == 31: self.call(o >> 8, o & 255)
        elif r == 32: self.sys = o
        elif r == 33: self.push(self.sys)
        elif r == 34:
            if not 1 <= self.bp <= 1024 or self.stack[self.bp-1] is None: raise RuntimeError('Invalid saved frame')
            self.sp = self.bp - 1; self.bp = self.stack[self.sp]
        elif r == 35: self.push(self.bp + self.stackAddress + signed(o))
        elif r == 36: self.push(-self.pop())
        elif r in (37,38): self.write(self.pri, self.read(self.pri) + (1 if r == 37 else -1))
        elif r == 40: jump()
        elif r == 41: self.ip = o
        elif r == 42:
            if self.pop(): jump()
        elif r == 43:
            if not self.pop(): jump()
        elif r == 44:
            if self.peek(): jump()
        elif r == 45:
            if not self.peek(): jump()
        elif r == 46:
            if self.pop() == self.pri: jump()
        elif r == 50: self.state = 'waiting'
        elif r == 51: self.state = 'halted'
        elif r == 62:
            value, pointer = self.pop(), self.pop(); self.write(pointer, value); self.push(value)
        elif r == 63: self.stack[self.sp-1] = self.read(self.peek())
        elif r == 64: self.push(self.read(o))
        elif r == 65: self.push(self.read(self.bp + self.stackAddress + signed(o)))
        elif r == 66: self.push(self.ip)
        elif r == 67: self.ip = self.pop() + 1
        elif r == 70:
            sp = self.peek()
            if sp > 1024: raise RuntimeError('Invalid stack pointer')
            self.sp = sp
        elif r == 72: self.push(self.bp)
        elif r == 74: self.bp = self.sp
        elif r in (90,91): self.push(r - 90)
        elif r == 92:
            if self.pri == o & 255: self._relative(o >> 8)
        elif 95 <= r <= 98: self.push(self.bp + self.stackAddress + r - 95)
        elif r in self.NOOPS or r == 0 or r > 98: pass
        else: raise RuntimeError('Unmapped raw opcode %s' % r)

    def _relative(self, operand): self.ip += signed(operand) - 1

    def snapshot(self):
        return copy.deepcopy({k:v for k,v in self.__dict__.items() if k not in ('program','host')})

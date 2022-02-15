def generate_lfsr(key):
    d = list(key * 2)
    seq = [0, 0, 0]

    seq[0] = 301989938
    seq[1] = 623357073
    seq[2] = -2004086252

    i = 0

    for i in range(0, 4):
        seq[0] = ord(d[i]) | (seq[0] << 8)
        seq[1] = ord(d[4 + i]) | (seq[1] << 8)
        seq[2] = ord(d[8 + i]) | (seq[2] << 8)

    seq[0] = seq[0] & 0xffffffff
    seq[1] = seq[1] & 0xffffffff
    seq[2] = seq[2] & 0xffffffff

    return seq


def byte_xor(b, seq):
    flag1 = 1
    flag2 = 0
    result = 0
    for _ in range(0, 8):
        v10 = (seq[0] >> 1)
        if (seq[0] << 31) & 0xffffffff:
            seq[0] = (v10 ^ 0xC0000031)
            v12 = (seq[1] >> 1)
            if (seq[1] << 31) & 0xffffffff:
                seq[1] = ((v12 | 0xC0000000) ^ 0x20000010)
                flag1 = 1
            else:
                seq[1] = (v12 & 0x3FFFFFFF)
                flag1 = 0
        else:
            seq[0] = v10
            v11 = (seq[2] >> 1)
            if (seq[2] << 31) & 0xffffffff:
                seq[2] = ((v11 | 0xF0000000) ^ 0x8000001)
                flag2 = 1
            else:
                seq[2] = (v11 & 0xFFFFFFF)
                flag2 = 0

        result = (flag1 ^ flag2 | 2 * result)
    return (result ^ b)


def data_xor(data):
    dat = list(data)
    s = generate_lfsr('a271730728cbe141e47fd9d677e9006d')
    for i in range(0, 128):
        dat[i] = byte_xor(dat[i], s)
    return bytes(dat)

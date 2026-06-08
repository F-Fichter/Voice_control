import sys
import tty
import termios


def read_key():
    """Read a single keypress. Returns a dict:
       {'key': 'digit'|'enter'|'esc'|'ctrl_space'|'ctrl_c'}
    """
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    if not ch:
        return {'key': 'none'}
    b = ord(ch)

    if ch == '\r' or ch == '\n':
        return {'key': 'enter'}
    if b == 27:  # ESC
        return {'key': 'esc'}
    if b == 0:   # Ctrl+Space / Ctrl+@
        return {'key': 'ctrl_space'}
    if b == 3:   # Ctrl+C
        return {'key': 'ctrl_c'}
    if b == ord('0'):
        return {'key': 'digit', 'value': 0}
    if ord('1') <= b <= ord('9'):
        return {'key': 'digit', 'value': b - ord('0')}
    return {'key': 'other', 'char': ch}

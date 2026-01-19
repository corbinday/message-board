import ascii5x5 as l
import color
import time

# import the display
import picounicorn

# set up the hardware
picounicorn.init()

# alphabet x and y pixel dimension
DIM = 5
DISPLAY_WIDTH = picounicorn.get_width()
print(f'display width: {DISPLAY_WIDTH}')

decoder = {
    'a': l.A,
    'b': l.B,
    'c': l.C,
    'd': l.D,
    'e': l.E,
    'f': l.F,
    'g': l.G,
    'h': l.H,
    'i': l.I,
    'j': l.J,
    'k': l.K,
    'l': l.L,
    'm': l.M,
    'n': l.N,
    'o': l.O,
    'p': l.P,
    'q': l.Q,
    'r': l.R,
    's': l.S,
    't': l.T,
    'u': l.U,
    'v': l.V,
    'w': l.W,
    'x': l.X,
    'y': l.Y,
    'z': l.Z,
    ' ': l.SPACE,
    '?': l.QUESTION_MARK,
    '.': l.PERIOD
}

BLANK = l.SPACE[0]

# turn message into array of pixel columns to display


def createMessageArray(message):
    # add blank to end of message
    # message.append('                ')

    messageArray = []
    # add padding to front of message
    padding = [BLANK for i in range(DISPLAY_WIDTH)]
    messageArray.extend(padding)

    # add message
    for c in message:
        for a in decoder[c.lower()]:
            messageArray.append(a)
        # add blank space to separate letters
        messageArray.append(BLANK)

    # pad the end of the message for spacing between runs
    messageArray.extend(padding)

    return messageArray


def displayFrame(frame, color):
    r, g, b = color
    # print(frame)
    # print('\n')
    for i in range(0, DISPLAY_WIDTH):
        for j in range(0, DIM):
            # print(f'({i}, {j})')
            # print(frame[i][j])
            if frame[i][j] == 1:
                picounicorn.set_pixel(i, j, r, g, b)
            else:
                picounicorn.set_pixel(i, j, 0, 0, 0)


def display(message, interval, color=color.RED):
    # create the message array
    messageArray = createMessageArray(message)
    # print(messageArray)

    # clear the screen
    picounicorn.clear()

    # on a set interval, move the message through the screen
    columns = len(messageArray)
    for i in range(0, columns):
        frame = list()
        # print(f'i:{i} of {columns}')
        for j in range(0, DISPLAY_WIDTH):

            if columns - i < (j + 1):
                c = BLANK
            else:
                c = messageArray[i + j]
            frame.append(c)

        # set columns into the screen
        displayFrame(frame, color)
        time.sleep(interval)


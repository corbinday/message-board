import ascii3x3 as l
import color
import time
# from breakout_bme68x import BreakoutBME68X
from breakout_rgbmatrix5x5 import BreakoutRGBMatrix5x5
from pimoroni_i2c import PimoroniI2C
from pimoroni import PICO_EXPLORER_I2C_PINS

# set up the hardware
i2c = PimoroniI2C(**PICO_EXPLORER_I2C_PINS)
#bme = BreakoutBME68X(i2c, address=0x76)
rgb = BreakoutRGBMatrix5x5(i2c, address=0x74)

# alphabet x and y pixel dimension
DIM = 3

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
    # message.append('     ')

    messageArray = []
    # add padding to front of message
    for i in range(DIM):
        messageArray.append(BLANK)

    # add message
    for c in message:
        for a in decoder[c.lower()]:
            messageArray.append(a)
        # add blank space to separate letters
        messageArray.append(BLANK)
    
    # pad the end of the message for spacing between runs
    messageArray.append(BLANK)

    return messageArray

def displayFrame(frame, color):
    r, g, b = color
    print(frame)
    print('\n')
    for i in range(0, 5):
            for j in range(0, DIM):
                print(f'({j}, {i})')
                if frame[i][j] == 1:
                    rgb.set_pixel(j + 1, i, r, g, b)
                else:
                    rgb.set_pixel(j + 1, i, 0, 0, 0)
    rgb.update()

def display(message, interval, color=color.RED):
    # create the message array
    messageArray = createMessageArray(message)
    print(messageArray)
   
    # clear the screen
    rgb.clear()
    rgb.update()

    
    
    # on a set interval, move the message through the screen
    columns = len(messageArray)
    for i in range(0, columns):
        print(f'i:{i} of {columns}')
        if columns - i < 1:
            col0 = BLANK
        else:
            col0 = messageArray[i]
        
        if columns - i < 2:
            col1 = BLANK
        else:
            col1 = messageArray[i + 1]
       
        if columns - i < 3:
            col2 = BLANK
        else:
            col2 = messageArray[i + 2]

        if columns - i < 4:
            col3 = BLANK
        else:
            col3 = messageArray[i + 3]

        if columns - i < 5:
            col4 = BLANK
        else:
            col4 = messageArray[i + 4]
    
        # set columns into the screen
        frame = [col0, col1, col2, col3, col4]
        displayFrame(frame, color)
        time.sleep(interval)


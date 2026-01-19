''' 
Code to connect a Pico W to wifi
see micropython>networking (https://docs.micropython.org/en/latest/esp8266/tutorial/network_basics.html)
'''

# ('happywifi', 'Asj9*qer')

def do_connect():
    import network
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('connecting to network...')
        sta_if.active(True)
        sta_if.connect('happywifi', 'Asj9*qer')
        while not sta_if.isconnected():
            pass
    print('network config:', sta_if.ifconfig())


do_connect()
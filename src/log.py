import logging

# Handles logging for this project via logger

def init_logger():    
    logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='dynload.log',
                    filemode='w')

    formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)

    fh = logging.FileHandler('hello.log')
    fh.setFormatter(formatter)

    logging.getLogger('').addHandler(ch)


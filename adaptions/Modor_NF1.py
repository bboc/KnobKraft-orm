"""
API description https://github.com/christofmuc/KnobKraft-orm/blob/master/adaptions/Adaptation%20Programming%20Guide.md
"""
from functools import reduce
import inspect
import hashlib
import operator
import sys
import textwrap


DEVICE_NAME = 'Modor NF-1(m)'
MANUFACTURER_NUMBER = [0x00, 0x21, 0x1c]
DEVICE_NUMBER = 0x01 # also works for NF-1m

START = 0xf0
SYSEX_HEADER = [START, *MANUFACTURER_NUMBER, DEVICE_NUMBER]
END = 0xf7

BANK_SIZE = 32
NUMBER_OF_BANKS = 14

DEFAULT_MIDI_CHANNEL = 9 # which mean 10? FFS!

# offset in patch_data, not in entire message!
NAME_OFFSET = 128
NAME_LEN = 10


# different types of sysex messages
EDIT_BUFFER_REQUEST = 0x05
PATCH_DUMP_NEW_STYLE = 0x09 # new style patch dump, used for edit buffer and patch memory dumps

PATCH_MEMORY_REQUEST =  0x0f # retreive patch from memory location request
SAVE_PATCH_TO_MEMORY = 0x10 # save patch in memory dump

BANK_DUMP = 0x0a # new style bank dump
MEMORY_DUMP =  0x0b # new style memory dump
MEMORY_DUMP_REQUEST = 0x0e #  Full memory dump request


# index of the packet number in a message
PACKET_NUMBER_IDX = 6

MAX_PACKET_LENGTH = 55

PATCH_DUMP_LENGTH = 55+55+34+ (7+2)*3  # 7 header (start, manufacturer, device, type, packet), 2 checksum and end)

# bytes 128:138 of the actual patch_data
NAME_CHARS = " 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz БВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ абвгдеёжзийклмнопрстуфхцчшщэюя" + '_' * 127

DEFAULT_NAME = "Init"

SYSEX_ACK_MESSAGE = [0xf0, 0x42, 0x30, 0x04, 0x41, 0xf7]

# 0: no log, 1: API, 2: API + local functions
LOGLEVEL = 1  


def _log(lvl,msg): 
    if LOGLEVEL >= lvl: print(':'* lvl, msg)


"""
Some notes:

In principle, you're always writing to the edit buffer. Sysex type 0x05 retrieves the edit buffer, 
0x09 overwrites it, and 0x11 and 0x12 change single parameter values in it. 

Types 0x0F and 0x10 are made to support librarian software to get and store patches on specific places 
in memory, without interfering with the edit buffer. 

Storage format is the PATCH_DUMP_NEW_STYLE reveved from edit buffer/program dump requests (which doesn't contain a memory location)

TODO: convert testing to pytest


"""
def _isMessageType(message, message_type):
    _log(2, "_isMessageType(message, {message_type})")
    """Return True if this is a sysex response from this device."""
    return (len(message) > 6
            and message[0:5] == SYSEX_HEADER
            and message[5] == message_type
            and message[-1] == END
            )

def test_isMessageType():
    _failUnless(_isMessageType(TEST_EDIT_BUFFER_DUMP, PATCH_DUMP_NEW_STYLE), 'message not recognized')
    _failUnless(_isMessageType(SYSEX_ACK_MESSAGE, PATCH_DUMP_NEW_STYLE) == False, 'wrong message recognized')


def _is_part_of_dump(message, dump_type):
    _log(2, f"_is_part_of_dump(message, '{dump_type}')")
    """Handle multi-MIDI message dump types."""
    if _isMessageType(message, dump_type):
       return True, SYSEX_ACK_MESSAGE
    else:
        return False 

def _splitProgramNumber(program_number):
    _log(2, f"_splitProgramNumber({program_number})")
    """Return bank and patch indexes from program_number"""
    bank = program_number // BANK_SIZE
    patch = program_number % BANK_SIZE
    return bank, patch

def test_splitProgramNumber():
    _failUnless(_splitProgramNumber(0) == (0,0))
    _failUnless(_splitProgramNumber(32) == (1,0))


def _extract_patch_data(message):
    _log(2, "_extract_patch_data(message)")
    """
    Extract the patch data from the 3 sysex messages.

    Structure: 
        - patch: 3 messages of max. 64 bytes, with a payload of 144 bytes (55, 55 and 34 bytes)
        - bank: 84 messages of max. 64 bytes, 32 x 144 bytes
    """
    
    offset = 7 # for patch dump new style
    if _isMessageType(message, SAVE_PATCH_TO_MEMORY):
        offset = 9
    patch_data = []
    for idx in range(3):
        packet = message[idx * 64 : (idx + 1) * 64]
        patch_data.extend(packet[offset:-2]) # remove header, potentially bank# and program# checksum+end
    return patch_data

def test_extract_patch_data():
    _failUnless(TEST_PATCH_DATA == _extract_patch_data(TEST_EDIT_BUFFER_DUMP), "could not extract patch data from PATCH_DUMP_NEW_STYLE")
    _failUnless(TEST_PATCH_DATA == _extract_patch_data(TEST_EDIT_BUFFER_DUMP), f"could not extract patch data from SAVE_PATCH_TO_MEMORY \n{TEST_SAVE_TO_MEMORY_DUMP} \n{_extract_patch_data(TEST_EDIT_BUFFER_DUMP)}")


def _calculate_checksum(payload):
    _log(2, "_calculate_checksum(payload)")
    """Calcluate a checksum for a list of integers (= a part of a message)."""
    return reduce(operator.xor, payload, 0)

def test_calculate_checksum():
    _failUnless(_calculate_checksum(TEST_PATCH_DATA[0:55]) == TEST_EDIT_BUFFER_DUMP[62])
    _failUnless(_calculate_checksum(TEST_PATCH_DATA[55:110]) == TEST_EDIT_BUFFER_DUMP[126])
    _failUnless(_calculate_checksum(TEST_PATCH_DATA[110:]) == TEST_EDIT_BUFFER_DUMP[-2])


def _pack_payload(payload, message_type):
    _log(2, f"_pack_payload(payload, {message_type})")
    """
    Pack a payload into several packages of message_type (with a max. payload length of 55 bytes per package).

    Payload is patch_data, or patch_data plus bank number and patch number
    """ 
    remaining_bytes = payload[:] # make a copy so that the original is not affected
    message = []
    packet_number = 0
    while remaining_bytes:
        packet_payload = remaining_bytes[0:MAX_PACKET_LENGTH]
        message.extend([
            *SYSEX_HEADER, message_type, 
            packet_number, *packet_payload, _calculate_checksum(packet_payload), 
            END])
        remaining_bytes = remaining_bytes[MAX_PACKET_LENGTH:]
        packet_number = packet_number + 1
    return message

def test_pack_payload():
    m = _pack_payload(TEST_PATCH_DATA, PATCH_DUMP_NEW_STYLE) 
    _failUnless(len(m) == len(TEST_EDIT_BUFFER_DUMP), len(m))
    _failUnless(m == TEST_EDIT_BUFFER_DUMP, _pack_payload(TEST_PATCH_DATA, PATCH_DUMP_NEW_STYLE))
    # unpack and repack needs to be the identical
    p = _extract_patch_data(TEST_EDIT_BUFFER_DUMP)
    m2 = _pack_payload(p, PATCH_DUMP_NEW_STYLE)
    _failUnless(m2 == TEST_EDIT_BUFFER_DUMP)

def _update_name_in_patch_data(patch_data, new_name):
    _log(2, f"_update_name_in_patch_data(patch_data, {new_name})")
    """Update (unicode) name in patch data."""
    return patch_data[:NAME_OFFSET] + _encode_name(new_name) + patch_data[NAME_OFFSET+NAME_LEN:]

def test_update_name_in_patch_data():
    new_name = "HuД9 12345"
    patch_data = _update_name_in_patch_data(TEST_PATCH_DATA, new_name)
    _failUnless(_get_name(patch_data) == new_name)
    _failUnless(_update_name_in_patch_data(TEST_PATCH_DATA, 'VeloNoizPS') == TEST_PATCH_DATA)


def _get_name(patch_data):
    _log(2, "_get_name(patch_data)")
    """extract (unicode) name from patch_data."""
    return _decode_name(patch_data[NAME_OFFSET:NAME_OFFSET + NAME_LEN])

def test_get_name():
    _failUnless(_get_name(TEST_PATCH_DATA) == 'VeloNoizPS', _get_name(TEST_PATCH_DATA))


def _decode_name(raw_name):
    _log(2, f"_decode_name('{raw_name}'')")
    """Decode a raw_name as stored in the sysex to unicode."""
    return ''.join([NAME_CHARS[char_idx] for char_idx in raw_name])

def test_decode_name():
    _failUnless(_decode_name([0]*NAME_LEN) == NAME_CHARS[0] * NAME_LEN)


def _encode_name(name):
    _log(2, f"_encode_name('{name}')")
    """Encode unicode string as patch data."""
    name = name[:NAME_LEN]
    if len(name) < NAME_LEN:
        name = name + (' ' * (NAME_LEN - len(name)))
    try: 
        return [NAME_CHARS.index(char) for char in name]
    except ValueError: 
        raise ValueError(f"unsupported character in '{name}'")

def test_encode_name():
    _failUnless(_encode_name(' 012345678') == [0,1,2,3,4,5,6,7,8,9], _encode_name(' 0123456789'))
    _failUnless(_encode_name(' 0123456789abcde') == [0,1,2,3,4,5,6,7,8,9], 'long name should be truncated')
    _failUnless(_encode_name(' 0') == [0,1,0,0,0,0,0,0,0,0], 'short name should be padded')
    try: 
        _encode_name('!@#$%^&*()')
    except ValueError:
        pass
    else:
        _failUnless(False, 'invalid character should raise index error')

"""
BASIC CONFIGURATION

KnobCraft will sent a message to test for the device on all outputs, and if necessary, on each MIDI port of each output.
"""


def name():
    _log(1,f"name(): '{DEVICE_NAME}'")
    """Return the name for that device."""
    return DEVICE_NAME


def bankDescriptors():
    _log(1,"bankDescriptors()")
    """
    Return a list of banks, and being described by dict:a the following fields in the Dict:

    "bank" [int] - The number of the bank. Should be zero-based
    "name" [str] - The friendly name of the bank
    "size" [int] - The number of items in this bank. This allows for banks of differenct sizes for one synth
    "type" [str] - A text describing the type of data in this bank. Could be "Patch", "Tone", "Song", "Rhythm" or whatever else is 
                   stored in banks. Will be displayed in the metadata.
    "isROM" [bool] - Use this to indicate for later bank management functionality that the bank can be read, but not written to
    """
    return [{"bank": b, "name": f"{friendlyBankName(b)}", "size": BANK_SIZE, "type": "Patch", 'isROM': False} for b in range(NUMBER_OF_BANKS)]


def bankSelect(channel, bank):
    _log(1,f"bankSelect({channel}, {bank})")
    """Midi message to select a specific bank in the device."""

    # CC#32 (Bank select)
    return [0xb0 | (channel & 0x0f), 32, bank] 


"""
DEVICE DETECTION

KnobCraft will sent a message to test for the device on all outputs, and if necessary, on each MIDI port of each output.
"""

def createDeviceDetectMessage(channel):
    _log(1,"createDeviceDetectMessage({channel})")
    """
    Return a single MIDI message or multiple MIDI messages in the form of a single list of byte-values integers used
    to detect the device.
    """
    # NF-1m doesn't support Device Inquiry, so let's fetch the edit buffer instead.
    return createEditBufferRequest(channel)


def deviceDetectWaitMilliseconds():
    _log(1,"deviceDetectWaitMilliseconds()")
    """
    Return the number of milliseconds the main program will wait for the synth to answer before it moves on testing 
    the next MIDI output.
    """
    return 200 # might not be necessary for NF-1(m)


def needsChannelSpecificDetection():
    _log(1,"needsChannelSpecificDetection()")
    """
    Return True if the createDeviceDetectMessage() should be called for each of the 16  MIDI channels on each 
    MIDI outputs, or False if it should only be called once per MIDI output.
    """
    # NF-1(m) doesn't need that.
    return False


def channelIfValidDeviceResponse(message):
    _log(1,"def channelIfValidDeviceResponse(message")
    """
    Test if the message correctly identifies the device. Return -1 if it doesn't.

    If it does, return a MIDI channel (0..15). If the message does not indicate a MIDI channel, just return a number.
    """
    # Response should be a single patch dump
    if _isMessageType(message, PATCH_DUMP_NEW_STYLE):
        # from that reply we cannot find out on which MIDI channel/Device ID the NF-1 is set up
        return DEFAULT_MIDI_CHANNEL
    return -1


"""
EDIT BUFFER CAPABILITY

This is probably the most common and intuitive capability, and most MIDI devices have the concept of an edit buffer.
A transient storage of the patch that is currentl being edited by the player. Normally, a  request method to retrieve 
the edit buffer as well as a send to edit buffer message exist. Sometimes, the request for an edit buffer is replied to
with a program dump, sometimes there is a specific edit buffer dump message.
"""

def createEditBufferRequest(channel):
    _log(1,"createEditBufferRequest({channel})")
    """Return a MIDI Message that requests the edit buffer."""
    return [*SYSEX_HEADER, EDIT_BUFFER_REQUEST, END]


def isEditBufferDump(message):
    _log(1,"isEditBufferDump(message)")
    """
    Return True if message is a valid Edit Buffer dump.

    TODO: fix the test problem:

    the problem here is that a request for the current edit buffer returns a patch dump (without memory location),
    and a request for a program dump also returns a patch dump. 
    but isEditBuffer() and isProgramDump() is also used in the tests because it is assumed that these are different.
    No idea what to do about this

    """
    return isSingleProgramDump(message)


def convertToEditBuffer(channel, message):
    _log(1,"convertToEditBuffer({channel}, message)")
    """
    Convert the message stored in the patch database to a message that updates the edit buffer in the synt. 
    Return message or messages (all in a single list of integers).
    """
    if isEditBufferDump(message):
        return message
    else:
        if _isMessageType(message, SAVE_PATCH_TO_MEMORY):
            # repack as edit buffer
            return _pack_payload(_extract_patch_data(message), PATCH_DUMP_NEW_STYLE)
        else:
            raise Exception(f"This message type can't be converted {message}")    


def isPartOfEditBufferDump(message):
    _log(1,"isPartOfEditBufferDump(message)")
    """
    For protocols that send multiple messages for one program dump, you can send a handshake.
    Return boolean, or boolean and a message
    """
    return isPartOfSingleProgramDump(message)

"""
PROGRAM DUMP CAPABILITY

To enable the Program Dump Capability for your adaptation, which will be used instead of the Edit Buffer Capability in 
enumerating the patches in the synth for download, you need to implement the following three functions:
"""


def createProgramDumpRequest(channel, program_number):
    _log(1,f"createProgramDumpRequest({channel}, {program_number})")
    """Return a request for for a specific patch."""

    bank, patch = _splitProgramNumber(program_number)
    return [*SYSEX_HEADER, PATCH_MEMORY_REQUEST, bank, patch, END]


def isSingleProgramDump(message):
    _log(1,"isSingleProgramDump(message)")    
    return (_isMessageType(message, PATCH_DUMP_NEW_STYLE)
            and len(message) == PATCH_DUMP_LENGTH
            and message.count(END) == 3) # 3 packets

def test_isSingleProgramDump():
    _failUnless(isSingleProgramDump(TEST_EDIT_BUFFER_DUMP))


def convertToProgramDump(channel, message, program_number):
    _log(1,f"convertToProgramDump({channel}, message, {program_number})")    
    """
    Update message stored in database so that it is sent to a specific position in the synths memory. 
    Requires Orm v2.0.0 and Modor OS >0.009.
    Works on PATCH_DUMP_NEW_STYLE and SAVE_PATCH_TO_MEMORY
    """
    
    if not _isMessageType(message, PATCH_DUMP_NEW_STYLE) or _isMessageType(message, SAVE_PATCH_TO_MEMORY):
        raise Exception("Can't convert this message type")

    # add bank and patch number to paylod 
    bank, patch = _splitProgramNumber(program_number)
    payload = [bank, patch]
    payload.extend(_extract_patch_data(message)) # this works on both types of sysex messages transparently
    pp = _pack_payload(payload, SAVE_PATCH_TO_MEMORY)
    return pp


def numberFromDump(message):
    _log(1,f"numberFromDump(message)")
    """Return the program number for a program dump."""

    # fail if message is not a patch memory dump
    assert _isMessageType(message, SAVE_PATCH_TO_MEMORY)
    bank = message[len(SYSEX_HEADER)+1]
    program = message[len(SYSEX_HEADER)+2]

    return bank*BANK_SIZE + program


def test_number_from_dump():

    program = numberFromDump(TEST_SAVE_TO_MEMORY_DUMP)
    _failUnless(program == 67, program) # Bank 2, Patch 3


def isPartOfSingleProgramDump(message):
    _log(1,"isPartOfSingleProgramDump(message)")    
    """Handle multi-MIDI message dump types exactly like the edit buffer capability."""
    return _is_part_of_dump(message, PATCH_DUMP_NEW_STYLE)

"""
BANK DUMP CAPABILITY

Some synths do no work with individual MIDI messages per patch, or even multiple MIDI messages for one patch, but 
rather with one big MIDI message which contains all patches of a bank. If your synth is of this type, you want to 
implement the following 4 functions to enable the Bank Dump Capability. Also, if you have only a single request to 
make, but the synth will reply with a stream of MIDI messages, this is the right capability to implement.

def createBankDumpRequest(channel, bank):

    UNAVALIABLE FOR THE NF1-m    

"""
# def createBankDumpRequest(channel, bank):
#     _log(1,f"createBankDumpRequest({channel}, {bank})")
#      return SYSEX_ACK_MESSAGE


def isPartOfBankDump(message):
    _log(1,"isPartOfBankDump(message)")
    return _is_part_of_dump(message, BANK_DUMP)


def isBankDumpFinished(message):
    _log(1,"isBankDumpFinished(message)")
    raise Exception("isBankDumpFinished!")
    return len(message) == 83 * 55 + 52
        

def extractPatchesFromBank(message):
    _log(1,"extractPatchesFromBank(message)")
    """
    Split bank dump into a list of single program messages.

    Bank dump: 32*144 data bytes = 83*55 + 43 bytes, 84 sysex packages
    """
    raise Exception("extractPatchesFromBank!")

    all_patch_data = _extract_patch_data(messages)
    patch_size = 144
    patches = []
    for idx in range(BANK_SIZE):
        patch_data = all_patch_data[idx * patch_size: idx*patch_size + patch_size]
        patches.append(_pack_payload(payload, PATCH_DUMP_NEW_STYLE))

    return patches


"""
OTHER FUNCTIONS
"""

def nameFromDump(message):
    _log(1,"nameFromDump(message)")
    """Getting the patch name from a patch dump."""
    return _get_name(_extract_patch_data(message))


def generalMessageDelay():
    _log(1,"generalMessageDelay()")
    """
    Return delay (in milliseconds) between two consecutive midi messages (the Orm will detect individual messages
    in the list automatically.
    """
    return 10


def renamePatch(message, new_name):
    _log(1,f"renamePatch(message, {new_name})")
    """
    Update the patch name in the MIDI message (edit buffer or program dump) with new_name. Might involve decoding, encoding and calculating checksums.
    Return MidiMessage with the renamed patch.
    """
    patch_data = _extract_patch_data(message)
    return _pack_payload(_update_name_in_patch_data(patch_data, new_name), PATCH_DUMP_NEW_STYLE)


def isDefaultName(patch_name):
    _log(1,f"isDefaultName({patch_name})")
    """
    Return True if the name is considered "Default", meaning without human intervention. Default names are given less priority when another name for the same patch is encountered.
    """
    return patch_name == DEFAULT_NAME


def calculateFingerprint(message):
    _log(1,"calculateFingerprint(message)")
    """
    Calculate unique key from all relevant data bytes of the patch to enable better duplicate detection.
    Typically this is done by blanking out all irrelevant bytes, (name, checksum etc.), and then hashing the result
    """
    # just hash the actual patch data
    patch_data = _extract_patch_data(message)
    # but blank the name before
    clean_data = _update_name_in_patch_data(patch_data, ' ' * NAME_LEN)
    return hashlib.md5(bytearray(clean_data)).hexdigest()  # Calculate the fingerprint from the cleaned patch data


def friendlyBankName(bank_number):
    _log(3,f"friendlyBankName({bank_number})")
    """
    Return a string to override default bank names ("Bank 1", "Bank 2", …) displayed whereever a patch location is shown in the Orm.
    
    Is used in places where adding "Bank " to bank name would result in "Bank Bank A"
    """
    return f"{chr(ord('A')+(bank_number))}"


def friendlyProgramName(program_number):
    _log(3,f"friendlyProgramName({program_number})")

    bank, patch_number = _splitProgramNumber(program_number)
    return f"{friendlyBankName(bank)}-{patch_number:02}"


# def numberOfLayers(message):
#    _log(1,"numberOfLayers(message")
#     """
#     Inspect the patch and return the number of layers in it.
#     """
#     # TODO: check if that needs to be o or 1 (or deleted)
#     return 0 # or 1?


# def setLayerName(self, message, layerNo, new_name):
#    _log(1,f"setLayerName(self, messages, layerNo, new_name))
#     """Return message with the specified layer's name changed to new_name."""
#     return message


# def storedTags(self, message):
#    _log(1,"TODO")
#     """
#     Return a list of strings that map to the categories defined im the KnobKraft database.
#     New categories can be imported in the Orm, so it's possible to use the manufacturer's category name, too.
#     """
#     # TODO: check if that needs to be removed


def setupHelp():
    """Return a text string to display any relevant information about how the synth needs to be set up in order to work with this adaptation."""
    return textwrap.dedent(name() + """ Setup Help:
        
        In SYSTEM SETTINGS:
        1. ProgChangeRx: ON
        2. SysexRx: ON

        Make sure the MIDI Channel in KnobCraft is correct, it can't be set automagically.
    """)

# a bit of test data for the automated tests
# single program dump
TEST_EDIT_BUFFER_DUMP = [
    0xf0, 0x00, 0x21, 0x1c, 0x01, 0x09, 0x00, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x34, 0x7d, 0x20, 0x31, 0x3a, 0x5c, 0x6b, 0x20, 0x4d, 0x5a, 0x6b, 0x23, 0x31, 0x5a, 0x78, 0x20, 0x64, 0x76, 0x20, 0x20, 0x7f, 0x40, 0x00, 0x30, 0x2b, 0x08, 0x00, 0x10, 0x40, 0x40, 0x40, 0x40, 0x40, 0x00, 0x3e, 0xf7,
    0xf0, 0x00, 0x21, 0x1c, 0x01, 0x09, 0x01, 0x7f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x58, 0x40, 0x7f, 0x18, 0x00, 0x00, 0x40, 0x20, 0x1c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40, 0x24, 0x40, 0x23, 0x40, 0x24, 0x40, 0x20, 0x7f, 0x7f, 0x7f, 0x7f, 0x7f, 0x7f, 0x7f, 0x7f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x07, 0x07, 0x07, 0x07, 0x67, 0xf7,
    0xf0, 0x00, 0x21, 0x1c, 0x01, 0x09, 0x02, 0x07, 0x0a, 0x04, 0x44, 0x10, 0x1f, 0x23, 0x0d, 0x0b, 0x1d, 0x54, 0x64, 0x50, 0x50, 0x64, 0x40, 0x40, 0x00, 0x20, 0x2a, 0x31, 0x34, 0x18, 0x34, 0x2e, 0x3f, 0x1a, 0x1d, 0x40, 0x43, 0x40, 0x40, 0x40, 0x0f, 0x57, 0xf7
]

TEST_SAVE_TO_MEMORY_DUMP = [
    0xf0, 0x00, 0x21, 0x1c, 0x01, 0x10, 0x02, 0x03, 0x00, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x34, 0x7d, 0x20, 0x31, 0x3a, 0x5c, 0x6b, 0x20, 0x4d, 0x5a, 0x6b, 0x23, 0x31, 0x5a, 0x78, 0x20, 0x64, 0x76, 0x20, 0x20, 0x7f, 0x40, 0x00, 0x30, 0x2b, 0x08, 0x00, 0x10, 0x40, 0x40, 0x40, 0x40, 0x40, 0x00, 0x3e, 0xf7,
    0xf0, 0x00, 0x21, 0x1c, 0x01, 0x10, 0x02, 0x03, 0x01, 0x7f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x58, 0x40, 0x7f, 0x18, 0x00, 0x00, 0x40, 0x20, 0x1c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40, 0x24, 0x40, 0x23, 0x40, 0x24, 0x40, 0x20, 0x7f, 0x7f, 0x7f, 0x7f, 0x7f, 0x7f, 0x7f, 0x7f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x07, 0x07, 0x07, 0x07, 0x67, 0xf7,
    0xf0, 0x00, 0x21, 0x1c, 0x01, 0x10, 0x02, 0x03, 0x02, 0x07, 0x0a, 0x04, 0x44, 0x10, 0x1f, 0x23, 0x0d, 0x0b, 0x1d, 0x54, 0x64, 0x50, 0x50, 0x64, 0x40, 0x40, 0x00, 0x20, 0x2a, 0x31, 0x34, 0x18, 0x34, 0x2e, 0x3f, 0x1a, 0x1d, 0x40, 0x43, 0x40, 0x40, 0x40, 0x0f, 0x57, 0xf7
]
# the patach data stored in that program dump
TEST_PATCH_DATA = [
    0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x34, 0x7d, 0x20, 0x31, 0x3a, 0x5c, 0x6b, 0x20, 0x4d, 0x5a, 0x6b, 0x23, 0x31, 0x5a, 0x78, 0x20, 0x64, 0x76, 0x20, 0x20, 0x7f, 0x40, 0x00, 0x30, 0x2b, 0x08, 0x00, 0x10, 0x40, 0x40, 0x40, 0x40, 0x40, 0x00,
    0x7f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x58, 0x40, 0x7f, 0x18, 0x00, 0x00, 0x40, 0x20, 0x1c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40, 0x24, 0x40, 0x23, 0x40, 0x24, 0x40, 0x20, 0x7f, 0x7f, 0x7f, 0x7f, 0x7f, 0x7f, 0x7f, 0x7f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x07, 0x07, 0x07, 0x07,
    0x07, 0x0a, 0x04, 0x44, 0x10, 0x1f, 0x23, 0x0d, 0x0b, 0x1d, 0x54, 0x64, 0x50, 0x50, 0x64, 0x40, 0x40, 0x00, 0x20, 0x2a, 0x31, 0x34, 0x18, 0x34, 0x2e, 0x3f, 0x1a, 0x1d, 0x40, 0x43, 0x40, 0x40, 0x40, 0x0f
]


def _run_tests():
    """Find all functions that start with "test_" in this module and run them."""
    globals()['LOGLEVEL'] = 1 # no logging during test execution
    globals()['FAILED'] = 0
    tests = [obj for name,obj in inspect.getmembers(sys.modules[__name__])
         if (inspect.isfunction(obj) and 
             name.startswith('test_') and
             obj.__module__ == __name__)]
    for test_func in tests:
        test_func()
    print(f"failed tests:{globals()['FAILED']}")
    
def _failUnless(condition, msg=None):
    location = f"{inspect.stack()[1].function} (line {inspect.stack()[1].lineno}) ::"
    if not condition:
        print(location, msg or 'error')
        globals()['FAILED'] += 1
    else:
        print(location, "✔")

def test_data():
    """Return a dictionary with test data."""

    def programs(messages):
        """
        Return return one or more programs:
        - message: the sysex message (as list of bytes)
        - name: the name of that patch

        """
        # yield dict(
        #     message=TEST_EDIT_BUFFER_DUMP,
        #     name='VeloNoizPS',
        #     is_edit_buffer=True, # with the Modor it's actually a program dump
        #     #target_no=0x02,
        # )
        yield dict(
            message=TEST_SAVE_TO_MEMORY_DUMP,
            name='VeloNoizPS',
            number=67, # which program number is expected in this dump
            is_edit_buffer=False, # with the Modor it's actually a program dump
            target_no=67, # no idea what this is for, but it needs to be set to the same value as "number"
        )

    return dict(
        # sysex="testData/MySyexFile.syx",  # sysex data to load, then the program generator can access the messages from that file
        program_generator=programs, 
        # convert_to_edit_buffer_produces_program_dump: False (appears to be a workaround for Alesis Andromeda)
        detection_reply=(
            TEST_EDIT_BUFFER_DUMP,  #  the message handed into channelIfValidDeviceResponse()
            9), # a midi channel that should come out
        # device_detect_call: the valid call produced by createDeviceDetectMessage for channel 0 (as string "FF EE 3A")
        # device_detect_reply: input for channelIfValidDeviceResponse() again as string "AA BB C3" that must return channel 1! 
        # program_dump_request: result of "createProgramDumpRequest() for bank 0, program 0 (as string)
        rename_name="new name",
        friendly_bank_name=(2, 'C')
    )


if __name__ == '__main__':
    """run all tests"""
    _run_tests()

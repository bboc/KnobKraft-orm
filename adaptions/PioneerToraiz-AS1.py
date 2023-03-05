#
#   Copyright (c) 2020 Christof Ruch. All rights reserved.
#
#   Dual licensed: Distributed under Affero GPL license by default, an MIT license is available for purchase
#

import hashlib

# start byte, 3x Pioneer ID, 3x Toraiz ID, Device ID (can't be changed in the device)
TORAIZ_HEADER = [0xf0, 0x00, 0x40, 0x05, 0x00, 0x00, 0x01, 0x08, 0x10]
END = 0xf7

GLOBAL_PARAMETER_REQUEST = 0x0e
GLOBAL_PARAMETER_DUMP = 0x0f

# [f0 00 40 05 00 00 01 08 10 0f 0c 32 00 04 00 02 02 01 01 02 01 01 00 00 00 01 04 03 00 00 00 01 02 03 04 05 06 07 08 09 0a 0b 0c 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 f7]
# [f0 00 40 05 00 00 01 08 10 0f 0c 32 03 04 00 02 02 01 01 02 01 01 00 00 00 01 04 03 00 00 00 01 02 03 04 05 06 07 08 09 0a 0b 0c 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 f7]

EDIT_BUFFER_REQUEST = 0x06
EDIT_BUFFER_DUMP = 0x03

PROGRAM_DUMP_REQUEST = 0x05
PROGRAM_DUMP = 0x02

# Length of patch name
NAME_LEN = 20
NAME_OFFSET = 107


BANK_SIZE = 99
NUMBER_OF_BANKS = 10


# 0: no log, 1: API, 2: API + local functions
LOGLEVEL = 0

def _log(lvl,msg):
    if LOGLEVEL >= lvl: print(':'* lvl, msg)


def name():
    return "Pioneer Toraiz AS-1"


def _isMessageType(message, message_type):
    _log(2, "_isMessageType(message, {message_type})")
    """Return True if this is a sysex response from this device with the given message_type."""
    return (len(message) > len(TORAIZ_HEADER) + 2
            and message[0:len(TORAIZ_HEADER)] == TORAIZ_HEADER
            and message[9] == message_type
            and message[-1] == END
            )


def numberOfBanks():
    return NUMBER_OF_BANKS

def numberOfPatchesPerBank():
    return BANK_SIZE

def isDefaultName(patch_name):
    _log(2, f"")
    return patch_name == "Basic Program"


def _splitProgramNumber(program_number):
    _log(2, f"_splitProgramNumber({program_number})")
    """Return bank and patch indexes from program_number"""
    bank = program_number // BANK_SIZE
    patch = program_number % BANK_SIZE
    return bank, patch

def friendlyBankName(bank_number):
    _log(1, f"friendlyBankName({bank_number})")
    """Convert bank numbers to bank names as displayed on the Toraiz AS-1."""
    if bank_number < 5:
        return f"U.{bank_number + 1}"
    return f"F.{bank_number - 4}"

def friendlyProgramName(program_number):
    _log(1, f"def friendlyProgramName({program_number})")
    bank, patch_number = _splitProgramNumber(program_number)
    return f"{friendlyBankName(bank)} P.{patch_number+1:02}"


def createDeviceDetectMessage(channel):
    _log(1, f"createDeviceDetectMessage({channel})")
    # See page 33 of the Toraiz AS-1 manual
    return [*TORAIZ_HEADER, GLOBAL_PARAMETER_REQUEST, END]


def needsChannelSpecificDetection():
    _log(1, f"needsChannelSpecificDetection()")
    return False


def channelIfValidDeviceResponse(message):
    _log(1, f"channelIfValidDeviceResponse({message})")
    # The manual states the AS1 replies with a 15 byte long message, see page 33
    if (len(message) == 59 and _isMessageType(message, GLOBAL_PARAMETER_DUMP)
        ):
        channel = message[12] # TODO: that should NOT work, but it does!
        print(f"found a Toraiz AS-1 on channel {channel}")
        if channel == 0: # The Toraiz is set to OMNI: just use channel 1
            return 0
        else:
            return channel - 1 # the channel in the AS-1 is not zero-based!
    return -1


def createEditBufferRequest(channel):
    _log(1, f"createEditBufferRequest({channel})")
    # See page 34 of the Toraiz manual
    return [*TORAIZ_HEADER, EDIT_BUFFER_REQUEST, END]


def isEditBufferDump(message):
    _log(1, f"isEditBufferDump(message)")
    # see page 35 of the manual
    return _isMessageType(message, EDIT_BUFFER_DUMP)


def createProgramDumpRequest(channel, patch_number):
    _log(1, f"createProgramDumpRequest({channel}, {patch_number})")
    # Calculate bank and program - the KnobKraft Orm will just think the patches are 0 to 999, but the Toraiz needs a
    # bank number 0-9 and the patch number within that bank
    bank, program = _splitProgramNumber(patch_number)
    # See page 33 of the Toraiz manual
    return [*TORAIZ_HEADER, PROGRAM_DUMP_REQUEST, bank, program, END]


def isSingleProgramDump(message):
    _log(1, f"isSingleProgramDump(message)")
    # see page 34 of the manual
    return _isMessageType(message, PROGRAM_DUMP)


def nameFromDump(message):
    _log(1, f"nameFromDump(message)")
    """Extract the patch name from the supplied sysex message."""
    patchData =_extract_patch_data(message)
    return ''.join([chr(c) for c in patchData[NAME_OFFSET:NAME_OFFSET+NAME_LEN]]).strip()


def renamePatch(message, new_name):
    _log(1, f"renamePatch(message, {new_name})")
    """Returns a copy of the supplied sysex message whose internal name has been replaced with new_name."""
    header, patchData = _extract_header_and_patch_data(message)
    patchData = _update_name_in_patch_data(patchData, new_name)
    # Rebuild the message with the new data block, appending "end of exclusive" (EOX).
    return header + _encode_8bit_to_7bit(patchData) + [END]


def calculateFingerprint(message):
    _log(1, f"calculateFingerprint(message)")
    """Calculates a hash from the message's data block only, ignoring the patch's name."""
    patchData = _extract_patch_data(message)
    patchData = _update_name_in_patch_data(patchData, '')
    return hashlib.md5(bytearray(patchData)).hexdigest()


def _update_name_in_patch_data(patchData, new_name):
    _log(2, f"_update_name_in_patch_data({patchData}, {new_name})")
    """Update name in decoded patch data, name might be empty."""
    # Normalize the name to 20 characters: add 20 spaces, then truncate
    name = new_name + " " * NAME_LEN
    name = name[:NAME_LEN]
    patchData[NAME_OFFSET:NAME_OFFSET+NAME_LEN] = map(ord, name)
    return patchData

def _extract_patch_data(message):
    _log(2, f"_extract_patch_data(message)")
    return _extract_header_and_patch_data(message)[1]

def _extract_header_and_patch_data(message):
    _log(2, f"_extract_header_and_patch_data(message)")
    """Return message header and the decoded data block from message, raise Exception if message type is unknown."""
    if isSingleProgramDump(message):
        dataBlockStart = 12
    elif isEditBufferDump(message):
        dataBlockStart = 10
    else:
        raise Exception(f"Unknown message type {message}")

    dataBlock = message[dataBlockStart:-1]
    if len(dataBlock) == 0:
        raise Exception("Data block length was 0.")

    patchData = _decode_7bit_to_8bit(dataBlock)
    return message[:dataBlockStart], patchData

def convertToEditBuffer(channel, message):
    _log(1, f"convertToEditBuffer({channel}, message)")
    if isEditBufferDump(message):
        return message
    if isSingleProgramDump(message):
        # remove the bank and program numben and switch the command
        return [*TORAIZ_HEADER, EDIT_BUFFER_DUMP, *message[12:]]
    raise Exception("Data is neither edit buffer nor single program buffer from Toraiz AS-1")


def convertToProgramDump(channel, message, program_number):
    _log(1, f"convertToProgramDump({channel}, message, {program_number})")
    bank, program = _splitProgramNumber(program_number)
    if isEditBufferDump(message):
        return message[0:9] + [PROGRAM_DUMP] + message[12:]
    elif isSingleProgramDump(message):
        return message[0:10] + [bank, program] + message[12:]
    raise Exception("Neither edit buffer nor program dump - can't be converted")


def _decode_7bit_to_8bit(sysex):
    _log(2, f"_decode_7bit_to_8bit(sysex)")
    """Decode a 7-bit sysex message to 8-bit bytes."""
    result = []
    dataIndex = 0
    while dataIndex < len(sysex):
        msbits = sysex[dataIndex]
        dataIndex += 1
        for i in range(7):
            if dataIndex < len(sysex):
                result.append(sysex[dataIndex] | ((msbits & (1 << i)) << (7 - i)))
            dataIndex += 1
    return result


def _encode_8bit_to_7bit(data):
    _log(2, f"_encode_8bit_to_7bit(data)")
    """Encode 8 bit data into 7-bit sysex format."""
    result = []
    msBits = 0
    byteIndex = 0
    chunk = []
    while byteIndex < len(data):
        indexInChunk = byteIndex % 7
        if indexInChunk == 0:
            chunk = []
        currentByte = data[byteIndex]
        lsBits = currentByte & 0x7F
        msBit = currentByte & 0x80
        msBits |= msBit >> (7 - indexInChunk)
        chunk.append(lsBits)
        if indexInChunk == 6 or byteIndex == len(data) - 1:
            chunk.insert(0, msBits)
            result += chunk
            msBits = 0
        byteIndex += 1
    return result


if __name__ == '__main__':
    """run all tests"""
    #_run_tests()
    print(friendlyProgramName(3))
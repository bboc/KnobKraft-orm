#
#   Copyright (c) 2022 Christof Ruch. All rights reserved.
#
#   Dual licensed: Distributed under Affero GPL license by default, an MIT license is available for purchase
#

import pytest
import knobkraft

import functools


def skip_targets_without_test_data(test_data_key=None):
    """Skip all adaptations that don't define test data."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not kwargs["test_data"]:
                pytest.skip(f"{kwargs['adaptation'].name()} has not defined test data.")
            if test_data_key and not test_data_key in kwargs['test_data'].test_dict:
                pytest.skip(f"{kwargs['adaptation'].name()} has not defined test data '{test_data_key}'")
            func(*args, **kwargs)

        return wrapper

    return decorator

def skip_targets_without(name):
    """Skip all adaptations that don't implement a certain function"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if name not in dir(kwargs['adaptation']):
                pytest.skip(f"{kwargs['adaptation'].name()} has not implemented {name}")
            func(*args, **kwargs)

        return wrapper

    return decorator


#
# Fixtures prepare the test data for the tests below
#
class AdaptationTestData:
    def __init__(self, adaptation):
        self.test_dict = adaptation.test_data()
        self.all_messages = []
        if "sysex" in self.test_dict:
            self.sysex_file = self.test_dict["sysex"]
            self.all_messages = knobkraft.load_sysex(self.sysex_file)
        if "program_generator" in self.test_dict:
            self.programs = list(self.test_dict["program_generator"](self.all_messages))
            self.program_dump = self.programs[0]["message"]
        if "detection_reply" in self.test_dict:
            self.detection_reply = self.test_dict["detection_reply"]


@pytest.fixture
def test_data(adaptation):
    if hasattr(adaptation, "test_data"):
        return AdaptationTestData(adaptation)
    else:
        return None


#
# These are generic tests every adaptation must pass
#
def test_name_is_not_none(adaptation):
    name = adaptation.name()
    assert name is not None
    assert isinstance(name, str)


@skip_targets_without_test_data("detection_reply")
def test_detection(adaptation, test_data: AdaptationTestData):
    assert adaptation.channelIfValidDeviceResponse(test_data.detection_reply[0]) == test_data.detection_reply[1]


@skip_targets_without_test_data()
@skip_targets_without("nameFromDump")
def test_extract_name(adaptation, test_data: AdaptationTestData):
    for program in test_data.programs:
        assert adaptation.nameFromDump(program["message"]) == program["name"]


@skip_targets_without_test_data()
@skip_targets_without("nameFromDump")
@skip_targets_without("renamePatch")
def test_rename(adaptation, test_data: AdaptationTestData):
    binary = test_data.program_dump
    # Rename to the name it already has
    renamed = adaptation.renamePatch(binary, adaptation.nameFromDump(binary))
    # This should not change the extracted name
    assert adaptation.nameFromDump(renamed) == adaptation.nameFromDump(binary)
    # This should not change the fingerprint
    if hasattr(adaptation, "calculateFingerprint"):
        assert adaptation.calculateFingerprint(renamed) == adaptation.calculateFingerprint(binary)
    # Now rename
    if "rename_name" in test_data.test_dict:
        new_name = test_data.test_dict["rename_name"]
    else:
        new_name = "new name"
    with_new_name = adaptation.renamePatch(binary, new_name)
    extracted_name = adaptation.nameFromDump(with_new_name)
    assert new_name.strip() == extracted_name.strip()


@skip_targets_without_test_data()
@skip_targets_without("isSingleProgramDump")
def test_is_program_dump(adaptation, test_data: AdaptationTestData):
    tested = False
    for program in test_data.programs:
        if not program.get("is_edit_buffer"):
            assert adaptation.isSingleProgramDump(program["message"])
            tested = True
    if not tested:
        pytest.skip(f"{adaptation.name} does not provide test data for test_is_program_dump()")


@skip_targets_without_test_data()
@skip_targets_without("isEditBufferDump")
def test_is_edit_buffer_dump(adaptation, test_data: AdaptationTestData):
    tested = False
    for program in test_data.programs:
        if program.get("is_edit_buffer"):
            assert adaptation.isEditBufferDump(program["message"])
            tested = True
    if not tested:
        pytest.skip(f"{adaptation.name()} does not provide test data for test_is_edit_buffer_dump()")

# this is the old test
@skip_targets_without_test_data()
def test_convert_to_edit_buffer(adaptation, test_data: AdaptationTestData):
    if hasattr(adaptation, "convertToEditBuffer") or hasattr(adaptation, "convertToProgramDump"):
        for program_data in test_data.programs:
            if "target_no" in program_data:
                target_no = program_data["target_no"]
            else:
                # Choose something random
                target_no = 11
            program = program_data["message"]
            if hasattr(adaptation, "isSingleProgramDump") and adaptation.isSingleProgramDump(program):
                previous_number = 0
                if hasattr(adaptation, "numberFromDump"):
                    previous_number = adaptation.numberFromDump(program)
                if hasattr(adaptation, "convertToEditBuffer"):
                    edit_buffer = adaptation.convertToEditBuffer(0x00, program)
                    if test_data.test_dict.get("convert_to_edit_buffer_produces_program_dump"):
                        # This is a special case for the broken implementation of the Andromeda edit buffer
                        assert adaptation.isSingleProgramDump(edit_buffer)
                    else:
                        # this relies on isEditBufferDump, but it's not tested
                        assert adaptation.isEditBufferDump(edit_buffer)
                if not hasattr(adaptation, "convertToProgramDump"):
                    # Not much more we can test here
                    continue
                if  test_data.test_dict.get("not_idempotent"):
                    pass
                else:
                    assert knobkraft.list_compare(program, adaptation.convertToProgramDump(0x00, program, previous_number))
                if hasattr(adaptation, "convertToEditBuffer"):
                    program_buffer = adaptation.convertToProgramDump(0x00, edit_buffer, target_no)
                else:
                    program_buffer = adaptation.convertToProgramDump(0x00, program, target_no)
            elif hasattr(adaptation, "isEditBufferDump") and adaptation.isEditBufferDump(program):
                program_buffer = adaptation.convertToProgramDump(0x00, program, target_no)
                assert adaptation.isSingleProgramDump(program_buffer)
                edit_buffer = adaptation.convertToEditBuffer(0x00, program_buffer)
            else:
                program_buffer = program
                edit_buffer = None
            if hasattr(adaptation, "numberFromDump"):
                assert adaptation.numberFromDump(program_buffer) == target_no
            if hasattr(adaptation, "nameFromDump") and edit_buffer is not None:
                assert adaptation.nameFromDump(program_buffer) == adaptation.nameFromDump(edit_buffer)
    else:
        pytest.skip(f"{adaptation.name} has not implemented convertToEditBuffer")

# these are the new tests
@skip_targets_without_test_data()
@skip_targets_without("convertToEditBuffer")
@skip_targets_without("isSingleProgramDump")
def test_convert_to_edit_buffer_(adaptation, test_data: AdaptationTestData):
    tested = False
    for program_data in test_data.programs:
        if "target_no" in program_data:
            target_no = program_data["target_no"]
        else:
            # Choose something random
            target_no = 11
        program = program_data["message"]
        if hasattr(adaptation, "isSingleProgramDump") and adaptation.isSingleProgramDump(program):
            previous_number = 0
            if hasattr(adaptation, "numberFromDump"):
                previous_number = adaptation.numberFromDump(program)
            if hasattr(adaptation, "convertToEditBuffer"):
                edit_buffer = adaptation.convertToEditBuffer(0x00, program)
                if "convert_to_edit_buffer_produces_program_dump" in test_data.test_dict and test_data.test_dict["convert_to_edit_buffer_produces_program_dump"]:
                    # This is a special case for the broken implementation of the Andromeda edit buffer
                    assert adaptation.isSingleProgramDump(edit_buffer)
                else:
                    assert adaptation.isEditBufferDump(edit_buffer)
            if not hasattr(adaptation, "convertToProgramDump"):
                # Not much more we can test here
                return
            if "not_idempotent" in test_data.test_dict:
                pass
            else:
                assert knobkraft.list_compare(program, adaptation.convertToProgramDump(0x00, program, previous_number))
            if hasattr(adaptation, "convertToEditBuffer"):
                program_buffer = adaptation.convertToProgramDump(0x00, edit_buffer, target_no)
            else:
                program_buffer = adaptation.convertToProgramDump(0x00, program, target_no)
        elif hasattr(adaptation, "isEditBufferDump") and adaptation.isEditBufferDump(program):
            program_buffer = adaptation.convertToProgramDump(0x00, program, target_no)
            assert adaptation.isSingleProgramDump(program_buffer)
            edit_buffer = adaptation.convertToEditBuffer(0x00, program_buffer)
        else:
            program_buffer = program
            edit_buffer = None
        if hasattr(adaptation, "numberFromDump"):
            assert adaptation.numberFromDump(program_buffer) == target_no
        if hasattr(adaptation, "nameFromDump") and edit_buffer is not None:
            assert adaptation.nameFromDump(program_buffer) == adaptation.nameFromDump(edit_buffer)
    if not tested: 
        pytest.skip(f"{adaptation.name} did not provide test data for testing convertToEditBuffer")

@skip_targets_without_test_data()
@skip_targets_without("convertToProgramDump")
@skip_targets_without("isEditBufferDump")
def test_convert_to_program_dup_(adaptation, test_data: AdaptationTestData):
    tested = False
    for program_data in test_data.programs:
        if "target_no" in program_data:
            target_no = program_data["target_no"]
        else:
            # Choose something random
            target_no = 11
        program = program_data["message"]
        if hasattr(adaptation, "isSingleProgramDump") and adaptation.isSingleProgramDump(program):
            previous_number = 0
            if hasattr(adaptation, "numberFromDump"):
                previous_number = adaptation.numberFromDump(program)
            if hasattr(adaptation, "convertToEditBuffer"):
                edit_buffer = adaptation.convertToEditBuffer(0x00, program)
                if "convert_to_edit_buffer_produces_program_dump" in test_data.test_dict and test_data.test_dict["convert_to_edit_buffer_produces_program_dump"]:
                    # This is a special case for the broken implementation of the Andromeda edit buffer
                    assert adaptation.isSingleProgramDump(edit_buffer)
                else:
                    assert adaptation.isEditBufferDump(edit_buffer)
            if not hasattr(adaptation, "convertToProgramDump"):
                # Not much more we can test here
                return
            if "not_idempotent" in test_data.test_dict:
                pass
            else:
                assert knobkraft.list_compare(program, adaptation.convertToProgramDump(0x00, program, previous_number))
            if hasattr(adaptation, "convertToEditBuffer"):
                program_buffer = adaptation.convertToProgramDump(0x00, edit_buffer, target_no)
            else:
                program_buffer = adaptation.convertToProgramDump(0x00, program, target_no)
        elif hasattr(adaptation, "isEditBufferDump") and adaptation.isEditBufferDump(program):
            program_buffer = adaptation.convertToProgramDump(0x00, program, target_no)
            assert adaptation.isSingleProgramDump(program_buffer)
            edit_buffer = adaptation.convertToEditBuffer(0x00, program_buffer)
        else:
            program_buffer = program
            edit_buffer = None
        if hasattr(adaptation, "numberFromDump"):
            assert adaptation.numberFromDump(program_buffer) == target_no
        if hasattr(adaptation, "nameFromDump") and edit_buffer is not None:
            assert adaptation.nameFromDump(program_buffer) == adaptation.nameFromDump(edit_buffer)
    if not tested: 
        pytest.skip(f"{adaptation.name} did not provide test data for testing convertToProgramDump")


@skip_targets_without_test_data()
@skip_targets_without("numberFromDump")
def test_number_from_dump(adaptation, test_data: AdaptationTestData):
    for program in test_data.programs:
        assert adaptation.numberFromDump(program["message"]) == program["number"]



@skip_targets_without_test_data()
@skip_targets_without("layerName")
def test_layer_name(adaptation, test_data: AdaptationTestData):
    for program in test_data.programs:
        assert adaptation.layerName(program["message"], 1) == program["second_layer_name"]
        assert adaptation.isSingleProgramDump(program["message"])
        new_messages = adaptation.setLayerName(program["message"], 1, 'changed layer')
        assert adaptation.layerName(new_messages, 1) == 'changed layer'
        assert adaptation.isSingleProgramDump(new_messages)


@skip_targets_without_test_data()
@skip_targets_without("calculateFingerprint")
def test_fingerprinting(adaptation, test_data: AdaptationTestData):
    for program in test_data.programs:
        md5 = adaptation.calculateFingerprint(program["message"])
        blank1 = None
        if hasattr(adaptation, "blankedOut"):
            blank1 = adaptation.blankedOut(program["message"])
        if hasattr(adaptation, "isSingleProgramDump") and hasattr(adaptation, "convertToProgramDump") and adaptation.isSingleProgramDump(
                program["message"]):
            # Change program place and make sure the fingerprint didn't change
            changed_position = adaptation.convertToProgramDump(0x09, program["message"], 0x31)
            if hasattr(adaptation, "blankedOut"):
                blank2 = adaptation.blankedOut(changed_position)
                assert knobkraft.list_compare(blank1, blank2)
            assert adaptation.calculateFingerprint(changed_position) == md5
        # Change name and make sure the fingerprint didn't change
        if hasattr(adaptation, "renamePatch"):
            renamed = adaptation.renamePatch(program["message"], "iixxoo")
            assert adaptation.calculateFingerprint(renamed) == md5


@skip_targets_without_test_data()
def test_device_detection(adaptation, test_data: AdaptationTestData):
    found = False
    if "device_detect_call" in test_data.test_dict:
        assert adaptation.createDeviceDetectMessage(0x00) == knobkraft.stringToSyx(test_data.test_dict["device_detect_call"])
        found = True
    if "device_detect_reply" in test_data.test_dict:
        assert adaptation.channelIfValidDeviceResponse(knobkraft.stringToSyx(test_data.test_dict["device_detect_reply"])) == 0x00
        found = True
    if not found:
        pytest.skip(f"{adaptation.name()} does provide test data for the device_detect_call or the device_detect_reply")


@skip_targets_without_test_data("program_dump_request")
def test_program_dump_request(adaptation, test_data: AdaptationTestData):
    assert knobkraft.list_compare(adaptation.createProgramDumpRequest(0x00, 0x00),
                                  knobkraft.stringToSyx(test_data.test_dict["program_dump_request"]))
 

@skip_targets_without_test_data("friendly_bank_name")
def test_friendly_bank_name(adaptation, test_data: AdaptationTestData):
    bank_data = test_data.test_dict["friendly_bank_name"]
    assert adaptation.friendlyBankName(bank_data[0]) == bank_data[1]

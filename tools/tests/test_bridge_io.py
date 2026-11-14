"""M2.2 transport mapping without requiring Arduino hardware."""
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "device" / "python"))
import bridge_io
import contracts


class FakeBridge:
    handlers = {}
    sent = []

    @classmethod
    def provide(cls, name, handler):
        cls.handlers[name] = handler

    @classmethod
    def notify(cls, *args):
        cls.sent.append(args)


class BridgeIOTest(unittest.TestCase):
    def setUp(self):
        FakeBridge.handlers = {}
        FakeBridge.sent = []
        self.module = types.ModuleType("arduino")
        self.module.app_utils = types.ModuleType("arduino.app_utils")
        self.module.app_utils.Bridge = FakeBridge
        self.modules = patch.dict(sys.modules, {"arduino": self.module,
                                                "arduino.app_utils": self.module.app_utils})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_receives_contract_messages_and_survives_bad_data(self):
        got = []
        bridge_io.start(got.append)
        handlers = FakeBridge.handlers
        handlers["env"](22.24, 41.26)
        handlers["knob_turn"](-1)
        handlers["knob_press"]()
        handlers["env"]("bad", 50)
        handlers["knob_turn"]("bad")
        handlers["knob_turn"](9)
        self.assertEqual(got, [{"t": 22.2, "rh": 41.3},
                               {"knob": "turn", "pos": -1}, {"knob": "press"}])

    def test_sends_every_command_without_rpc_calls(self):
        messages = [{"face": "smile"}, {"face": "feedback", "pos": 1},
                    {"face": "text", "text": "LATER"}, {"beep": "low"}]
        for msg in messages:
            bridge_io.send(msg)
        self.assertEqual(FakeBridge.sent, [("face", "smile"),
                                           ("face_feedback", 1),
                                           ("face_text", "LATER"), ("beep", "low")])
        with self.assertRaises(contracts.ContractError):
            bridge_io.send({"face": "invalid"})
        self.assertEqual(len(FakeBridge.sent), 4)


if __name__ == "__main__":
    unittest.main()

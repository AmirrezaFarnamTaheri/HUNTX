"""Offline regression checks; never use real proxy credentials as fixtures."""
import base64
import json

import pytest

from scripts.assemble_generated_snapshot import add_clean_remark as assemble_remark
from huntx.formats.npvt import add_clean_remark as runtime_remark


def decode_payload(uri):
    return json.loads(base64.b64decode(uri.partition("#")[0][8:], validate=True))


@pytest.mark.parametrize("add_clean_remark", [assemble_remark, runtime_remark])
@pytest.mark.parametrize("index", range(1, 6))
def test_vmess_payload_remark_is_cleaned_and_fragment_preserved(index, add_clean_remark):
    payload = {
        "add": "example.invalid",
        "port": "443",
        "id": "00000000-0000-4000-8000-000000000001",
        "ps": "old source remark",
    }
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    uri = f"vmess://{encoded}#%73ource-{index}"
    counter = {"vmess": index - 1}

    result = add_clean_remark(uri, counter)

    assert result.partition("#")[2] == f"%73ource-{index}"
    assert decode_payload(result) == {**payload, "ps": f"vmess-{index}"}
    assert counter == {"vmess": index}


@pytest.mark.parametrize("add_clean_remark", [assemble_remark, runtime_remark])
def test_undecodable_vmess_is_preserved_not_rewritten(add_clean_remark):
    uri = "vmess://not-valid-base64!#source"
    assert add_clean_remark(uri, {}) == uri

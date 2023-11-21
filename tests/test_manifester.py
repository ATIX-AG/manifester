from unittest.mock import Mock

from functools import cached_property
from requests import request
from manifester import Manifester
from manifester.settings import settings
from manifester.helpers import MockStub, fake_http_response_code
import pytest
import random

def test_basic_init(manifest_category="golden_ticket"):
    """Test that manifester can initialize with the minimum required arguments and verify that resulting object has an access token attribute"""

    manifester_inst = Manifester(manifest_category=manifest_category, requester=RhsmApiStub(in_dict=None))
    assert isinstance(manifester_inst, Manifester)
    assert manifester_inst.access_token == "this is a simulated access token"

class RhsmApiStub(MockStub):

    def __init__(self, in_dict=None, **kwargs):
        self._good_codes = kwargs.get("good_codes", [200])
        self._bad_codes = kwargs.get("bad_codes", [429, 500, 504])
        self._fail_rate = kwargs.get("fail_rate", 10)
        super().__init__(in_dict)

    @cached_property
    def status_code(self):
        return fake_http_response_code(self._good_codes, self._bad_codes, self._fail_rate)

    def post(self, *args, **kwargs):
        """Simulate responses to POST requests for RHSM API endpoints used by Manifester"""

        if args[0].endswith("openid-connect/token"):
            self.access_token = "this is a simulated access token"
            return self
        if args[0].endswith("allocations"):
            self.uuid = "1234567890"
            return self
        if args[0].endswith("entitlements"):
            self.params = kwargs["params"]
            return self

    def get(self, *args, **kwargs):
        """"Simulate responses to GET requests for RHSM API endpoints used by Manifester"""

        if args[0].endswith("versions"):
            self.version_response = {'body': [
                {'value': 'sat-6.14', 'description': 'Satellite 6.14'},
                {'value': 'sat-6.13', 'description': 'Satellite 6.13'},
                {'value': 'sat-6.12', 'description': 'Satellite 6.12'}
            ]}
            return self
        if args[0].endswith("pools"):
            self.body = [{'id': '987adf2a8977', 'subscriptionName': 'Red Hat Satellite Infrastructure Subscription', 'entitlementsAvailable': 13}]
            return self
        if "allocations" in args[0] and not ("export" in args[0] or "pools" in args[0]):
            self.allocation_data = "this allocation data also includes entitlement data"
            return self
        if args[0].endswith("export"):
            self.body = {'exportJobID': '123456', 'href': 'exportJob'}
            return self
        if "exportJob" in args[0]:
            del self.status_code
            if self.force_export_failure:
                self._good_codes = [202]
            else:
                self._good_codes = [202, 200]
            self.body = {'exportID': 27, 'href': 'https://example.com/export/98ef892ac11'}
            return self
        if "export" in args[0] and not args[0].endswith("export"):
            del self.status_code
            self._good_codes = [200]
            # Manifester expects a bytes-type object to be returned as the manifest
            self.content = b"this is a simulated manifest"
            return self

    def delete(self, *args, **kwargs):
        """Simulate responses to DELETE requests for RHSM API endpoints used by Manifester"""

        if args[0].endswith("allocations/1234567890") and kwargs["params"]["force"] == "true":
            del self.status_code
            self.content = b""
            self._good_codes=[204]
            return self


def test_create_allocation():
    """Test that manifester's create_subscription_allocation method returns a UUID"""

    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict=None))
    allocation_uuid = manifester.create_subscription_allocation()
    assert allocation_uuid.uuid == "1234567890"

def test_negative_simple_retry_timeout():
    """Test that exceeding the attempt limit when retrying a failed API call results in an exception"""

    # TODO: figure out why this test fails despite raising the expected exception
    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict=None, fail_rate=100))
    with pytest.raises(Exception) as exception:
        manifester.create_subscription_allocation()
    assert str(exception.value) == "Retry timeout exceeded"

def test_negative_manifest_export_timeout():
    """Test that exceeding the attempt limit when exporting a manifest results in an exception"""

    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict={"force_export_failure": True}))
    with pytest.raises(Exception) as exception:
        manifester.get_manifest()
    assert str(exception.value) == "Export timeout exceeded"

def test_get_manifest():
    """Test that manifester's get_manifest method returns a manifest"""

    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict=None))
    manifest = manifester.get_manifest()
    assert manifest.content.decode("utf-8") == "this is a simulated manifest"
    assert manifest.status_code == 200

def test_delete_subscription_allocation():
    """Test that manifester's delete_subscription_allocation method deletes a subscription allocation"""

    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict=None))
    manifester.get_manifest()
    response = manifester.delete_subscription_allocation()
    assert response.status_code == 204
    assert response.content == b""

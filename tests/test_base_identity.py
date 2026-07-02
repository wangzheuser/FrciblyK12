import pytest

from core.base_identity import MailboxIdentityProvider
from core.base_mailbox import MailboxAccount


class _Mailbox:
    def get_email(self):
        return MailboxAccount(email="base@example.com", account_id="base@example.com")

    def get_current_ids(self, account):
        return {"old-message"}


def test_mailbox_identity_allows_plus_alias_for_same_mailbox():
    identity = MailboxIdentityProvider(mailbox=_Mailbox()).resolve("base+e2e@example.com")

    assert identity.email == "base+e2e@example.com"
    assert identity.mailbox_account.email == "base@example.com"
    assert identity.before_ids == {"old-message"}


def test_mailbox_identity_rejects_unrelated_requested_email():
    with pytest.raises(ValueError, match="不一致"):
        MailboxIdentityProvider(mailbox=_Mailbox()).resolve("other@example.com")

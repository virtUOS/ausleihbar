# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Custom model fields."""

from django.db import models

from .encryption import decrypt, encrypt


class EncryptedTextField(models.TextField):
    """A text field whose value is transparently encrypted at rest.

    The in-memory Python value is always plaintext; the database column always
    holds Fernet ciphertext. Because ciphertext is non-deterministic, the field
    is not meant for filtering/uniqueness — only for storing opaque secrets.
    """

    description = "Text stored encrypted at rest"

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None:
            return value
        return encrypt(value)

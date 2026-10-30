import unittest

from fastapi import HTTPException

from server.documents import MAX_FILE_BYTES, validate_file


class UploadValidationTests(unittest.TestCase):
    def assert_rejected(self, filename, content, status):
        with self.assertRaises(HTTPException) as error:
            validate_file(filename, content)
        self.assertEqual(error.exception.status_code, status)

    def test_valid_text_and_pdf(self):
        self.assertEqual(validate_file("notes.TXT", b"Hello")[0], "notes.TXT")
        self.assertEqual(validate_file("notes.pdf", b"%PDF-1.7\n")[1], "application/pdf")

    def test_filename_cannot_preserve_directory_segments(self):
        self.assertEqual(validate_file("C:\\private\\notes.txt", b"Hello")[0], "notes.txt")

    def test_empty_and_oversized_uploads(self):
        self.assert_rejected("notes.txt", b"", 400)
        self.assert_rejected("notes.txt", b"a" * (MAX_FILE_BYTES + 1), 413)

    def test_content_must_match_supported_type(self):
        self.assert_rejected("notes.html", b"hello", 415)
        self.assert_rejected("notes.pdf", b"not a pdf", 400)
        self.assert_rejected("notes.txt", b"\xff\x00", 400)

    def test_control_characters_in_names_are_rejected(self):
        self.assert_rejected("notes\n.txt", b"hello", 400)

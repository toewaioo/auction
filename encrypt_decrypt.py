import random
import base64
import struct # To pack/unpack integers into bytes

class A3Cipher:
    """
    An optimized and more robust version of the A3 Encryption/Decryption.
    Uses bytes and Base64 encoding to handle binary XOR output safely.
    """
    # A delimiter unlikely to appear in Base64 output
    # Note: Base64 uses A-Z, a-z, 0-9, +, /, and = for padding.
    # A different character or sequence is needed. Let's use '::'
    DELIMITER = b'::'

    def __init__(self):
        """
        Initializes the cipher object with a new random key.
        This randomKey will be included in each message payload.
        """
        # Use a larger range for randomKey to be more robust against collisions
        # and potential patterns, though still not cryptographically secure.
        # Max value for a 32-bit integer is 2**32 - 1 = 4294967295
        self.randomKey = random.randint(10000, 4294967295)

    def _integer_to_bytes(self, integer_value: int) -> bytes:
        """Converts an integer to bytes using a fixed size (4 bytes for simplicity)."""
        # Use little-endian byte order
        return struct.pack('<I', integer_value)

    def _bytes_to_integer(self, byte_data: bytes) -> int:
        """Converts bytes back to an integer."""
        # Use little-endian byte order
        return struct.unpack('<I', byte_data)[0]

    def start_encryption(self, text: str, key_string: str) -> str:
        """
        Encrypts the given text using XOR with derived keys.
        The encrypted data and keys are Base64 encoded for safe transmission.
        """
        try:
            # 1. Encode the input text to bytes (e.g., UTF-8)
            text_bytes = text.encode('utf-8')

            # 2. Calculate totalKey from the key_string
            totalKey = sum(ord(char) for char in key_string)
            # Ensure totalKey is within a reasonable range if needed,
            # but XOR handles larger numbers fine. Let's keep it as is for now.

            # 3. Perform the double XOR encryption on bytes
            encrypted_bytes_list = []
            # Iterate through bytes
            for byte_in_text in text_bytes:
                # XOR with totalKey
                xored_byte = byte_in_text ^ totalKey
                # XOR with randomKey
                double_xored_byte = xored_byte ^ self.randomKey
                # The result can be larger than a single byte (0-255).
                # We need to handle this. A simple XOR on bytes might produce
                # results outside the byte range if keys are large.
                # Let's apply the XOR byte by byte with keys treated as cyclical streams.
                # A more common XOR stream cipher approach is to use the key bytes directly
                # or derive a key stream. Sticking to the original's integer XOR idea,
                # but applying it per byte, requires careful handling of potential overflow
                # if the result exceeds 255 before the second XOR.
                # A direct XOR `byte ^ key` where key is large doesn't make sense byte-wise.
                # Let's reinterpret the original logic: The *integer* result of the XORs
                # was cast to a *character*. This implies the original intended state per
                # original character might have been a larger integer.
                # To replicate this with bytes, we'd need to convert each input byte
                # to an integer, XOR it, and then figure out how to represent the result as bytes.
                # The simplest way to adapt the original integer logic to bytes safely is to:
                # Convert byte to int, XOR with int keys, then convert the resulting int back to bytes.
                # However, mapping an arbitrary integer result back to a single byte is lossy.

                # Let's assume the original intent, despite the flawed chr/ord usage, was a simple
                # byte-wise XOR with potentially large integer keys affecting the bit pattern.
                # A standard way to apply an integer key in a byte-wise XOR is to use its byte representation cyclically
                # or, as the original attempted, effectively XORing the *integer value* of the byte.
                # The original code `ord(char_in_text) ^ totalKey ^ self.randomKey` performs two integer XORs.
                # The result is an integer. The fundamental error is `chr()`ing this potentially large int.
                # To fix this, we must keep the result as integers or convert them to a suitable byte representation.
                # Since the original expected `chr()` to produce *one* character per input character,
                # this implies an assumption the final XOR result would fit into a character's code point.
                # A more robust approach: XOR the *byte value* with the *byte values* from the keys.
                # This requires using byte streams from the keys.

                # Let's use a stream cipher approach derived from the keys for optimization and correctness.
                # We can combine totalKey and randomKey into a single effective key stream.
                # The simplest interpretation of the original's XOR logic applied byte-wise:
                effective_key_per_byte = (totalKey + self.randomKey) % 256 # A simple combination for a per-byte XOR value
                encrypted_byte = byte_in_text ^ effective_key_per_byte
                encrypted_bytes_list.append(encrypted_byte)

            encrypted_data_bytes = bytes(encrypted_bytes_list)

            # 4. Convert keys to bytes for inclusion in the payload
            totalKey_bytes = self._integer_to_bytes(totalKey)
            randomKey_bytes = self._integer_to_bytes(self.randomKey)

            # 5. Base64 encode the encrypted data and keys
            encoded_data = base64.b64encode(encrypted_data_bytes)
            encoded_totalKey = base64.b64encode(totalKey_bytes)
            encoded_randomKey = base64.b64encode(randomKey_bytes)

            # 6. Combine the encoded parts with the delimiter
            # The delimiter itself should also be bytes
            payload_bytes = encoded_data + self.DELIMITER + encoded_totalKey + self.DELIMITER + encoded_randomKey

            # 7. Return the final payload as a string
            return payload_bytes.decode('ascii') # Base64 is ASCII safe

        except Exception as e:
            print(f"[ENCRYPTION_ERROR] An error occurred during encryption: {e}")
            raise # Re-raise the exception


class A3Decipher:
    """Decryption class for A3Cipher, stateless as keys come from payload."""
    DELIMITER = b'::' # Must match the cipher

    def startDecryption(self, encrypted_payload: str) -> str:
        """
        Decrypts the payload. Keys and encrypted data are extracted,
        Base64 decoded, and then used for XOR decryption.
        """
        try:
            # 1. Convert the payload string back to bytes
            payload_bytes = encrypted_payload.encode('ascii') # Base64 is ASCII

            # 2. Split the payload bytes using the delimiter
            parts = payload_bytes.split(self.DELIMITER)

            if len(parts) != 3:
                raise ValueError("Invalid encrypted payload format: Incorrect number of segments.")

            encoded_data, encoded_totalKey, encoded_randomKey = parts

            # 3. Base64 decode the segments
            encrypted_data_bytes = base64.b64decode(encoded_data)
            totalKey_bytes = base64.b64decode(encoded_totalKey)
            randomKey_bytes = base64.b64decode(encoded_randomKey)

            # 4. Convert key bytes back to integers
            totalKey_from_payload = self._bytes_to_integer(totalKey_bytes)
            randomKey_from_payload = self._bytes_to_integer(randomKey_bytes)

            # 5. Perform the double XOR decryption on bytes
            decrypted_bytes_list = []
            # Apply the same effective key derivation as in encryption
            effective_key_per_byte = (totalKey_from_payload + randomKey_from_payload) % 256

            for encrypted_byte in encrypted_data_bytes:
                # Reverse the XOR operation
                original_byte = encrypted_byte ^ effective_key_per_byte
                decrypted_bytes_list.append(original_byte)

            decrypted_bytes = bytes(decrypted_bytes_list)

            # 6. Decode the decrypted bytes back to a string
            decrypted_text = decrypted_bytes.decode('utf-8')

            return decrypted_text

        except (ValueError, base64.binascii.Error, struct.error) as e:
            # Catch errors related to splitting, Base64 decoding, or struct unpacking
            print(f"[DECRYPTION_ERROR] Data format or decoding error: {e}")
            raise # Re-raise for the client to handle
        except Exception as e:
            print(f"[DECRYPTION_ERROR] An unexpected error occurred during decryption: {e}")
            raise # Re-raise

    def _bytes_to_integer(self, byte_data: bytes) -> int:
        """Converts bytes back to an integer."""
        # Use little-endian byte order - must match encryption
        if len(byte_data) != 4:
             raise ValueError(f"Invalid key byte length: Expected 4 bytes, got {len(byte_data)}")
        return struct.unpack('<I', byte_data)[0]

    def _integer_to_bytes(self, integer_value: int) -> bytes:
         """Converts an integer to bytes using a fixed size (4 bytes for simplicity)."""
         # Use little-endian byte order - included here for completeness though
         # primarily used in A3Cipher.encrypt.
         return struct.pack('<I', integer_value)


# --- Example Usage ---
if __name__ == "__main__":
    cipher = A3Cipher()
    key_string = "MySecretPassword123"
    original_message = "This is a test message with some characters including symbols !@#$%^&*() and numbers 12345."

    print(f"Original Message: {original_message}")
    print(f"Using key string: {key_string}")
    print(f"Generated randomKey: {cipher.randomKey}")

    try:
        encrypted_payload = cipher.encrypt(original_message, key_string)
        print(f"Encrypted Payload (Base64): {encrypted_payload}")

        decipher = A3Decipher()
        decrypted_message = decipher.decrypt(encrypted_payload)
        print(f"Decrypted Message: {decrypted_message}")

        # Verify decryption
        if original_message == decrypted_message:
            print("\nDecryption successful!")
        else:
            print("\nDecryption failed!")
            print(f"Original: {original_message}")
            print(f"Decrypted: {decrypted_message}")

    except Exception as e:
        print(f"\nAn error occurred during the process: {e}")

    print("-" * 20)

    # Example with a different message
    original_message_2 = "Hello, World! Привет мир!" # Message with non-ASCII characters
    print(f"Original Message 2: {original_message_2}")

    try:
        # Reuse the same cipher instance (and its randomKey) or create a new one
        cipher2 = A3Cipher()
        encrypted_payload_2 = cipher2.encrypt(original_message_2, key_string) # Use the same key string
        print(f"Encrypted Payload 2 (Base64): {encrypted_payload_2}")

        decipher2 = A3Decipher()
        decrypted_message_2 = decipher2.decrypt(encrypted_payload_2)
        print(f"Decrypted Message 2: {decrypted_message_2}")

        if original_message_2 == decrypted_message_2:
             print("\nDecryption 2 successful!")
        else:
             print("\nDecryption 2 failed!")
             print(f"Original: {original_message_2}")
             print(f"Decrypted: {decrypted_message_2}")

    except Exception as e:
         print(f"\nAn error occurred during process 2: {e}")

    print("-" * 20)

    # Example of invalid payload
    print("Testing decryption with invalid payload...")
    invalid_payload = "thisisnotavalidpayload"
    try:
        decipher3 = A3Decipher()
        decipher3.decrypt(invalid_payload)
    except ValueError as e:
        print(f"Caught expected error for invalid payload: {e}")
    except Exception as e:
        print(f"Caught unexpected error for invalid payload: {e}")

    print("-" * 20)

    # Example of invalid Base64 in payload
    print("Testing decryption with invalid Base64...")
    invalid_b64_payload = f"{base64.b64encode(b'encrypted').decode('ascii')}::{base64.b64encode(struct.pack('<I', 123)).decode('ascii')}::invalidbase64"
    try:
        decipher4 = A3Decipher()
        decipher4.decrypt(invalid_b64_payload)
    except base64.binascii.Error as e:
        print(f"Caught expected error for invalid Base64: {e}")
    except Exception as e:
         print(f"Caught unexpected error for invalid Base64: {e}")
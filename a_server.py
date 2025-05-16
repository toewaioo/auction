import random
from socket import socket
from encrypt_decrypt import A3Cipher,A3Decipher
class Server:
    def __init__(self, client_socket: socket): # Corrected constructor name
        self.client: socket = client_socket
        # It's generally better to generate keys per session or use more robust key exchange.
        # For this example, keeping your structure but noting this point.
        self.randomKey = random.randint(10000, 999999)
        # self.encrypted_data = '' # This seems like a temporary variable for encryption, not instance state

    def _binary_to_char_representation(self, binary_str: str) -> str:
        """Converts a 16-bit binary string to a single character."""
        if len(binary_str) != 16:
            # This is where the error originates
            raise ValueError(f"Binary string must be 16 bits long for char representation, got {len(binary_str)}")
        decimal_value = int(binary_str, 2)
        return chr(decimal_value)

    def _start_encryption(self, text: str, key_string: str) -> str:
        encrypted_data_parts = [] # Or whatever you called this list
        totalKey = sum(ord(char) for char in key_string)

        for char_in_text in text:
            encrypted_ord = ord(char_in_text) ^ totalKey
            # self.randomKey is the Server instance's random key for this connection
            double_encrypted_ord = encrypted_ord ^ self.randomKey

            # ---- START FIX ----
            # Mask the result to ensure it's a 16-bit value
            double_encrypted_ord_masked = double_encrypted_ord & 0xFFFF
            # ---- END FIX ----

            # Now, format the masked value. This will always be 16 bits (padded if necessary).
            double_encrypted_binary = format(double_encrypted_ord_masked, '016b')
            
            encrypted_data_parts.append(self._binary_to_char_representation(double_encrypted_binary))

        encrypted_main_part = "".join(encrypted_data_parts)

        totalKey_binary = bin(totalKey)[2:]
        # self.randomKey is the instance specific randomKey used in XORing above
        randomKey_binary = bin(self.randomKey)[2:]

        return f"{encrypted_main_part}X{totalKey_binary}X{randomKey_binary}"

    def _ensure_multiple_of_sixteen(self, binary_str: str) -> str: # Renamed based on usage (016b)
        """
        Ensures the binary string length is a multiple of sixteen by adding zeros.
        """
        remainder = len(binary_str) % 16
        if remainder != 0:
            zeros_needed = 16 - remainder
            binary_str += '0' * zeros_needed
        return binary_str

    def _binary_to_char_representation(self, binary_str: str) -> str:
        """
        Converts a 16-bit binary string to a single character.
        This assumes the resulting decimal value is a valid character code.
        Be cautious if binary_str can represent values outside printable ASCII/Unicode range,
        or values that might conflict with delimiters (like 'X').
        """
        # Ensure it's 16 bits before converting, or handle errors
        if len(binary_str) != 16:
             # This case should ideally not happen if format(..., '016b') is used correctly.
            raise ValueError(f"Binary string must be 16 bits long for char representation, got {len(binary_str)}")
        decimal_value = int(binary_str, 2)
        return chr(decimal_value)


    def _char_to_16bit_binary(self, char_val: str) -> str:
        """
        Converts a single character (from the encrypted string part) to its 16-bit binary representation.
        """
        if len(char_val) != 1:
            raise ValueError("Input must be a single character.")
        return format(ord(char_val), '016b')


    def _start_decryption(self, encrypted_payload: str) -> str: # Made protected
        """
        Alternative decryption method using binary operations.
        """
        decrypted_text_chars = []
        try:
            parts = encrypted_payload.split('X')
            if len(parts) < 3: # Should have at least data, totalKey_binary, randomKey_binary
                raise ValueError("Invalid encrypted payload format: Missing delimiters 'X'")

            encrypted_data_segment = parts[0]
            # Assuming the last two parts are always totalKey_binary and randomKey_binary
            totalKey_from_payload = int(parts[-2], 2)
            randomKey_from_payload = int(parts[-1], 2) # This should match self.randomKey if encryption was done by this instance

            # Important: For decryption to work correctly if randomKey is part of the payload
            # and also an instance variable, they MUST match.
            # If randomKey is generated fresh on Server instantiation and NOT passed in payload for decryption,
            # then the sender must have used the SAME randomKey.
            # Your current encryption sends randomKey in the payload, so we use that.

            for char_from_encrypted_segment in encrypted_data_segment:
                # Convert the character (representing 2 bytes of encrypted data) back to 16-bit binary
                double_encrypted_ord_binary = self._char_to_16bit_binary(char_from_encrypted_segment)
                double_encrypted_ord = int(double_encrypted_ord_binary, 2)

                encrypted_ord = double_encrypted_ord ^ randomKey_from_payload # First XOR undo
                original_char_ord = encrypted_ord ^ totalKey_from_payload    # Second XOR undo
                decrypted_text_chars.append(chr(original_char_ord))

        except ValueError as e:
            print(f"[DECRYPTION_ERROR] {e} - Payload: {encrypted_payload[:50]}...") # Log error and part of payload
            raise # Re-raise the exception to signal failure
        except Exception as e:
            print(f"[DECRYPTION_ERROR] Unexpected error: {e} - Payload: {encrypted_payload[:50]}...")
            raise

        return "".join(decrypted_text_chars)

    # Public methods for encryption/decryption
    def decrypt(self, encrypted_data_str: str) -> str:
        """Decrypts data received from the client."""
        # print(f"Decrypting: {encrypted_data_str[:60]}...") # For debugging
        return self._start_decryption(encrypted_data_str)

    def encrypt(self, data_to_send: str, key: str) -> str:
        """Encrypts data to be sent to the client."""
        # print(f"Encrypting: {data_to_send[:60]}... with key material: {key}") # For debugging
        return self._start_encryption(data_to_send, key) # key is the "server secret key"

    def send(self, msg: str):
        """Encrypts and sends a message to the client."""
        try:
            print(f"[SEND_RAW] {self.client.getpeername()}: {msg}") # Debug: original message
            encrypted_msg = A3Cipher().start_encryption(msg, "server secret key") # Use a consistent secret key
            print(f"[SEND_ENCRYPTED] {self.client.getpeername()}: {encrypted_msg[:60]}...") # Debug: encrypted message
            self.client.sendall(encrypted_msg.encode("utf-8")) # Ensure encoding
        
        except Exception as e:
            print(f"[ERROR] Failed to send message to {self.client.getpeername()}: {e}")
            raise

    def recv(self, buffer_size=4096) -> str: # Increased buffer size, make it configurable if needed
        """Receives, decodes, and decrypts a message from the client."""
        # Note: TCP is a stream protocol. A single send() might require multiple recv() calls,
        # and a single recv() might get multiple messages if sent quickly.
        # A robust solution uses message delimiters or length prefixes.
        # This implementation assumes one recv() gets one complete encrypted message.
        try:
            encrypted_data_bytes = self.client.recv(buffer_size)
            if not encrypted_data_bytes:
                return "" # Connection closed by client

            encrypted_data_str = encrypted_data_bytes.decode("utf-8") # Ensure decoding
            # print(f"[RECV_ENCRYPTED] {self.client.getpeername()}: {encrypted_data_str[:60]}...") # Debug
            decrypted_msg = A3Decipher().startDecryption(encrypted_data_str)
            # print(f"[RECV_DECRYPTED] {self.client.getpeername()}: {decrypted_msg}") # Debug
            return decrypted_msg
        except ConnectionResetError:
            print(f"[INFO] Connection reset by peer {self.client.getpeername()}.")
            return "" # Treat as disconnection
        except UnicodeDecodeError as e:
            print(f"[ERROR] Unicode decode error for {self.client.getpeername()}: {e}. Data: {encrypted_data_bytes[:60]}")
            raise # Or return an error indicator
        except ValueError as e: # Catch decryption errors (e.g., format issues)
             print(f"[ERROR] Decryption failed for {self.client.getpeername()}: {e}")
             raise # Or return an error indicator
        except Exception as e:
            print(f"[ERROR] Failed to receive/decrypt message from {self.client.getpeername()}: {e}")
            raise
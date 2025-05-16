# client.py (Improved)
import json
import re
import socket
import threading
import time # For potential timeouts or delays, though not heavily used yet
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any # <--- ADD THIS LINE

# Use the corrected encryption/decryption module
from encrypt_decrypt import A3Cipher, A3Decipher

# --- Global Variables & Configuration ---
SERVER_HOST = "127.0.0.1"  # Server's IP address
SERVER_PORT = 5561   # Server's port (make sure this matches server.py)

# Socket object (initialized later)
client_socket: Optional[socket.socket] = None

# Encryption/Decryption objects
# A new randomKey is generated for this client session by A3Encryption()
encrypt_util = A3Cipher()
decrypt_util = A3Decipher()
# Key string used by this client to encrypt messages sent TO the server.
# The server must be configured to use this same key string to decrypt these messages.
CLIENT_ENCRYPTION_KEY = "client_key_string"


# For live updates
live_update_active_item_id: Optional[int] = None
live_update_thread: Optional[threading.Thread] = None
receive_thread: Optional[threading.Thread] = None
stop_event = threading.Event() # Use one event for signaling threads to stop

logged_in_user: Optional[dict] = None


# --- Network Functions ---
def connect_to_server(host: str, port: int) -> Optional[socket.socket]:
    """Establishes connection to the server."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        sock.settimeout(10.0) # Timeout for blocking socket operations
        print(f"Connected to server at {host}:{port}")
        return sock
    except socket.error as e:
        print(f"Error connecting to server: {e}")
        return None

def send_message(sock: socket.socket, command_data: str) -> bool:
    """Encrypts and sends a message to the server."""
    if sock is None:
        print("Not connected to server.")
        return False
    try:
        encrypted_message = encrypt_util.start_encryption(command_data, CLIENT_ENCRYPTION_KEY)
        sock.sendall(encrypted_message.encode('utf-8'))
        # print(f"[DEBUG Sent] {command_data} -> {encrypted_message[:30]}...") # For debugging
        return True
    except socket.error as e:
        print(f"Error sending message: {e}")
        stop_event.set() # Signal other threads if connection is broken
        return False
    except Exception as e:
        print(f"An unexpected error occurred during send: {e}")
        return False


def receive_message(sock: socket.socket, buffer_size: int = 8192) -> Optional[str]:
    """Receives, decodes, and decrypts a message from the server."""
    if sock is None:
        print("Not connected to server.")
        return None
    try:
        encrypted_data_bytes = sock.recv(buffer_size)
        if not encrypted_data_bytes:
            print("Connection closed by server (received empty data).")
            stop_event.set()
            return None
        
        encrypted_data_str = encrypted_data_bytes.decode('utf-8')
        # print(f"[DEBUG Recv Enc] {encrypted_data_str[:30]}...") # For debugging
        decrypted_message = decrypt_util.startDecryption(encrypted_data_str)
        # print(f"[DEBUG Recv Dec] {decrypted_message}") # For debugging
        return decrypted_message
    except socket.timeout:
        # This is normal if no data is incoming and a timeout is set on the socket.
        # The receive_messages_loop handles this by continuing.
        return "SOCKET_TIMEOUT"
    except UnicodeDecodeError as e:
        print(f"Error decoding message: {e}. Data: {encrypted_data_bytes[:60]}")
        return None
    except ValueError as e: # Catch decryption errors from A3Decryption
        print(f"Error decrypting message: {e}.")
        return None # Or an error string
    except socket.error as e:
        print(f"Socket error receiving message: {e}")
        stop_event.set() # Signal other threads
        return None
    except Exception as e:
        print(f"An unexpected error occurred during receive: {e}")
        stop_event.set()
        return None

def execute_command(command_str: str) -> Optional[str]:
    """Sends a command and waits for a single response."""
    global client_socket
    if client_socket is None:
        print("Not connected. Cannot send command.")
        return None
    if send_message(client_socket, command_str):
        return receive_message(client_socket)
    return None

# --- Input Validation & UI Helpers ---
def get_non_empty_input(prompt: str) -> str:
    """Gets non-empty input from the user."""
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Input cannot be empty. Please try again.")

def is_valid_email_format(email: str) -> bool:
    """Validates email format using regex."""
    email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    return bool(re.match(email_pattern, email))

def check_email_availability_on_server(email: str) -> Optional[bool]:
    """Checks if email exists on the server."""
    response = execute_command(f"check_email,{email}")
    if response == "SUCCESS":
        return True  # Email exists
    elif response == "FAIL":
        return False # Email does not exist
    return None # Error or unknown response

# --- User & Auction Functions ---
def register_user():
    global client_socket
    print("\n--- User Registration ---")
    username = get_non_empty_input("Enter username: ")
    
    while True:
        email = get_non_empty_input("Enter email address: ")
        if not is_valid_email_format(email):
            print("Invalid email format.")
            continue
        available = check_email_availability_on_server(email)
        if available is True:
            print("Email already exists. Please use a different email or login.")
            return # Or ask for a different email
        elif available is None:
            print("Could not verify email with server. Registration aborted.")
            return
        break # Email is valid format and does not exist on server

    password = get_non_empty_input("Enter password: ")
    contact = get_non_empty_input("Enter contact details: ")
    
    while True:
        try:
            balance_str = get_non_empty_input("Enter your initial balance: ")
            balance = int(balance_str)
            if balance < 0:
                print("Balance cannot be negative.")
                continue
            break
        except ValueError:
            print("Invalid balance. Please enter a number.")

    # Client should send data in a structured way, JSON is good.
    user_data = {"username": username, "email": email, "password": password, "contact": contact, "balance": balance}
    user_data_json = json.dumps(user_data) # Send as JSON string

    response = execute_command(f"add_user,{user_data_json}") # Server expects JSON after '-'
    
    if response == "SUCCESS":
        print("Registration successful.")
    elif response == "FAIL_FORMAT":
        print("Registration failed: Invalid data format sent to server.")
    else:
        print("Registration failed. Please try again.")

def login_user():
    global client_socket, logged_in_user
    print("\n--- User Login ---")
    email = get_non_empty_input("Enter email address: ")
    if not is_valid_email_format(email):
        print("Invalid email format.")
        return

    password = get_non_empty_input("Enter password: ")
    
    response = execute_command(f"login,{email},{password}")

    if response and response != "FAIL":
        try:
            user_data = json.loads(response)
            logged_in_user = user_data
            print(f"Login successful. Welcome, {logged_in_user.get('username', 'User')}!")
        except json.JSONDecodeError:
            print("Login failed: Received invalid data from server.")
            logged_in_user = None
    else:
        print("Login failed: Invalid email or password.")
        logged_in_user = None

def logout_user():
    global logged_in_user
    logged_in_user = None
    # Optionally, send a logout message to the server if needed for session management on server-side
    # execute_command("logout")
    print("You have been logged out.")


def display_auctions():
    global client_socket
    print("\n--- Auction Listings ---")
    choice = input("View (1) Active Auctions or (2) Ended Auctions? [1]: ")
    list_type = "1" if choice == "1" else "0" # Server: "1" for active (not ended), "0" for ended (or adjust server logic)
    # My server refactor uses ended=True (so "1") for *not ended* and ended=False ("0") for *ended*
    # Let's make client match: "1" for not_ended (active), "0" for ended.
    # Server's filter_auctions(self, ended=False)
    # ended=True means client wants auctions that ARE NOT ENDED YET.
    # ended=False means client wants auctions that ARE ENDED.
    # So if client types 1 (Active), we send "1" to server (ended=True)
    # If client types 2 (Ended), we send "0" to server (ended=False)

    server_command_param = "1" if choice == "1" else "0"

    response = execute_command(f"auction_list,{server_command_param}")
    if not response:
        print("Could not fetch auction list.")
        return

    try:
        auctions = json.loads(response)
        if not auctions:
            print("No auctions found in this category.")
            return

        for auction in auctions:
            end_time = datetime.strptime(auction['end_time'], '%Y-%m-%d %H:%M')
            time_now = datetime.now()
            is_ended_client_calc = time_now >= end_time
            
            status = "Ended" if is_ended_client_calc else "Open"
            print(f"\n--- Auction ID: {auction['id']} | Status: {status} ----")
            print(f"  Title: {auction['title']}")
            print(f"  Description: {auction['description']}")
            print(f"  Base Price: ${auction.get('base_price', 'N/A')}")
            print(f"  End Time: {auction['end_time']}")
            
            if is_ended_client_calc:
                print(f"  Sold to: {auction.get('highest_bidder', 'N/A')} with bid ${auction.get('highest_bid', 'N/A')}")
            else:
                remaining_str = format_time_remaining(end_time - time_now)
                print(f"  Time Remaining: {remaining_str}")
                if auction.get('highest_bidder'):
                    print(f"  Highest Bid: ${auction['highest_bid']} by {auction['highest_bidder']}")
                else:
                    print("  No bids yet.")
            print(f"  Seller: {auction['seller']}")
        print("-" * 30)

    except json.JSONDecodeError:
        print("Error: Could not parse auction data from server.")

def format_time_remaining(time_delta: timedelta) -> str:
    """Formats timedelta into a human-readable string."""
    if time_delta.total_seconds() <= 0:
        return "Ended"
    days = time_delta.days
    hours, remainder = divmod(time_delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {int(hours)}h {int(minutes)}m {int(seconds)}s"


def place_bid():
    global client_socket, logged_in_user
    if not logged_in_user:
        print("You must be logged in to place a bid.")
        return
    print("\n--- Place a Bid ---")
    try:
        item_id_str = get_non_empty_input("Enter the ID of the item you want to bid on: ")
        item_id = int(item_id_str)
    except ValueError:
        print("Invalid item ID format.")
        return

    # Optionally, first check item status before asking for bid amount
    item_status_response = execute_command(f"check_item,{item_id}")
    if not item_status_response or item_status_response.startswith("BAD") or "ended" in item_status_response.lower():
        print(f"Cannot bid on this item. Status: {item_status_response}")
        return
    print(f"Current status for item {item_id}:\n{item_status_response}")

    try:
        bid_amount_str = get_non_empty_input("Enter your bid amount: $")
        bid_amount = float(bid_amount_str)
        if bid_amount <= 0:
            print("Bid amount must be positive.")
            return
    except ValueError:
        print("Invalid bid amount format.")
        return

    response = execute_command(f"bid,{logged_in_user['id']},{item_id},{bid_amount}")
    if response == "OK":
        print("Bid placed successfully!")
        # If bid is successful, user might want to see live updates for this item
        confirm_live = input(f"Do you want to receive live updates for item {item_id}? (yes/no): ").lower()
        if confirm_live == 'yes':
            start_live_updates_for_item(item_id)
    else:
        print(f"Bid failed: {response}")


def create_new_auction():
    global client_socket, logged_in_user
    if not logged_in_user:
        print("You must be logged in to create an auction.")
        return
    print("\n--- Create New Auction ---")
    title = get_non_empty_input("Enter auction title: ")
    description = get_non_empty_input("Enter auction description: ")
    img_url = get_non_empty_input("Enter product image URL: ")
    
    while True:
        try:
            base_price_str = get_non_empty_input("Enter base price: $")
            base_price = int(base_price_str)
            if base_price < 0:
                print("Base price cannot be negative.")
                continue
            break
        except ValueError:
            print("Invalid base price. Please enter a number.")
            
    while True:
        try:
            duration_hours_str = get_non_empty_input("Enter auction duration in hours (e.g., 1, 24): ")
            duration_hours = int(duration_hours_str)
            if duration_hours <= 0:
                print("Duration must be positive.")
                continue
            break
        except ValueError:
            print("Invalid duration. Please enter a number of hours.")

    end_time = datetime.now() + timedelta(hours=duration_hours)
    end_time_str = end_time.strftime('%Y-%m-%d %H:%M') # Format expected by server

    command_str = f"create_auction,{title},{description},{img_url},{base_price},{end_time_str},{logged_in_user['username']}"
    response = execute_command(command_str)

    if response and response != "FAIL":
        print(f"Auction item created successfully with ID: {response}")
    else:
        print("Auction creation failed.")


# --- Live Update Functions ---
def receive_messages_loop():
    """Dedicated thread for receiving and printing all incoming messages from server."""
    global client_socket
    print("[Live Update Listener Started]")
    while not stop_event.is_set() and client_socket:
        message = receive_message(client_socket)
        if message is None: # Indicates a critical error or connection closed
            print("[Live Update Listener] Connection lost or error. Stopping.")
            stop_event.set()
            break
        if message == "SOCKET_TIMEOUT": # Normal timeout, continue listening
            continue
        
        # Process different types of server messages if server sends structured updates
        # Example: LIVE_UPDATE,ITEM_ID,TIME_REMAINING,CURRENT_BID_INFO
        # WINNER_NOTIFICATION,ITEM_ID,MESSAGE
        # AUCTION_ENDED,ITEM_ID,LAST_PRICE,WINNER_INFO
        parts = message.split(',', 3)
        msg_type = parts[0]

        if msg_type == "LIVE_UPDATE" and len(parts) >= 4:
            item_id, time_rem, bid_info = parts[1], parts[2], parts[3]
            if live_update_active_item_id == int(item_id): # Only print if user is watching this item
                 print(f"\n[LIVE ITEM {item_id}] Time: {time_rem}, {bid_info}")
        elif msg_type in ["WINNER_NOTIFICATION", "AUCTION_ENDED"]:
            # These are general notifications, always print them
            print(f"\n[Notification] {message}")
        else:
            # General message or unformatted update
            print(f"\n[Server Message] {message}")

    print("[Live Update Listener Stopped]")


def handle_live_item_input():
    """Manages user input for selecting and stopping live auction item views."""
    global client_socket, logged_in_user, live_update_active_item_id
    
    if not logged_in_user: # Should have been checked before starting this thread
        print("Error: User not logged in for live updates.")
        return

    print("\n--- Live Auction Monitoring ---")
    print("Enter item ID to monitor, or type 'exit' to stop monitoring and return to menu.")

    while not stop_event.is_set():
        try:
            user_input = input("Monitor item ID (or 'exit'): ").strip().lower()
            if not user_input: # Handle if user just presses Enter
                continue

            if user_input == 'exit':
                if live_update_active_item_id is not None:
                    print(f"Stopping live updates for item {live_update_active_item_id}.")
                    send_message(client_socket, f"stop_live_update,{live_update_active_item_id},{logged_in_user['id']}")
                    live_update_active_item_id = None
                break # Exit this input loop

            item_id_to_monitor = int(user_input)
            if live_update_active_item_id is not None and live_update_active_item_id != item_id_to_monitor:
                # Stop previous before starting new
                send_message(client_socket, f"stop_live_update,{live_update_active_item_id},{logged_in_user['id']}")
            
            print(f"Requesting live updates for item {item_id_to_monitor}...")
            # Server sends initial status upon this request
            if send_message(client_socket, f"live_auction,{item_id_to_monitor},{logged_in_user['id']}"):
                live_update_active_item_id = item_id_to_monitor
            else:
                print(f"Failed to request live updates for item {item_id_to_monitor}.")
                live_update_active_item_id = None # Ensure it's reset if request fails

        except ValueError:
            print("Invalid item ID. Please enter a number or 'exit'.")
        except KeyboardInterrupt: # Allow Ctrl+C to exit this specific input loop
            print("\nExiting live monitoring input...")
            if live_update_active_item_id is not None:
                send_message(client_socket, f"stop_live_update,{live_update_active_item_id},{logged_in_user['id']}")
                live_update_active_item_id = None
            break
        if stop_event.is_set(): # Check if main stop signal was given
            break
    print("--- Exited Live Auction Monitoring Input ---")


def start_live_updates_for_item(item_id: int):
    """Helper to directly start live updates for a specific item, e.g., after a bid."""
    global client_socket, logged_in_user, live_update_active_item_id, receive_thread, live_update_thread

    if not logged_in_user:
        print("Please login to use live updates.")
        return
    if not client_socket:
        print("Not connected to server.")
        return

    # Ensure receive_thread is running
    if receive_thread is None or not receive_thread.is_alive():
        print("Restarting message listener for live updates...")
        stop_event.clear() # Clear if it was set before
        receive_thread = threading.Thread(target=receive_messages_loop, daemon=True)
        receive_thread.start()
    
    # Stop monitoring previous item if any
    if live_update_active_item_id is not None and live_update_active_item_id != item_id:
        send_message(client_socket, f"stop_live_update,{live_update_active_item_id},{logged_in_user['id']}")

    print(f"Requesting live updates for item {item_id}...")
    if send_message(client_socket, f"live_auction,{item_id},{logged_in_user['id']}"):
        live_update_active_item_id = item_id
        print(f"Now monitoring item {item_id}. Messages will appear below. Press Enter to return to menu or type commands.")
        # The live_update_thread (for input) is not started here, user returns to main menu
        # and messages are printed by receive_messages_loop.
        # If a dedicated input loop for live updates is needed, call handle_live_item_input() in a new thread.
    else:
        print(f"Failed to request live updates for item {item_id}.")
        live_update_active_item_id = None


def manage_live_updates_session():
    """Starts the live update input loop and ensures message receiver is running."""
    global logged_in_user, receive_thread, live_update_thread

    if not logged_in_user:
        print("Please login to use live updates.")
        return
    if not client_socket:
        print("Not connected to server.")
        return
        
    # Ensure the main message receiving thread is active
    if receive_thread is None or not receive_thread.is_alive():
        print("Starting message listener for live updates...")
        stop_event.clear()
        receive_thread = threading.Thread(target=receive_messages_loop, daemon=True)
        receive_thread.start()

    # Start or ensure the input handling thread for live updates is active
    # This function handle_live_item_input will run its own loop for user commands like 'exit' or item_id
    # It will block until that loop is exited.
    handle_live_item_input()
    # After handle_live_item_input finishes, the user is back to the main menu.
    # The receive_thread continues in the background if not stopped.

# --- Profile Management ---
def view_profile():
    global logged_in_user
    if not logged_in_user:
        print("You need to be logged in to view your profile.")
        return

    # Fetch latest user data
    refresh_response = execute_command(f"login,{logged_in_user['email']},{logged_in_user['password']}")
    if refresh_response and refresh_response != "FAIL":
        try:
            logged_in_user = json.loads(refresh_response) # Update local copy
        except json.JSONDecodeError:
            print("Could not refresh profile data.")
            # Continue with potentially stale data or return
    else:
        print("Could not refresh profile data. Displaying cached info.")


    print(f"\n--- User Profile: {logged_in_user.get('username')} ---")
    print(f"  Username: {logged_in_user.get('username')}")
    print(f"  Email:    {logged_in_user.get('email')}")
    # print(f"  Password: {'*' * len(logged_in_user.get('password', ''))}") # Don't display password
    print(f"  Contact:  {logged_in_user.get('contact')}")
    print(f"  Balance:  ${logged_in_user.get('balance', 0.0):.2f}")
    print("------------------------------------")

    while True:
        print("\nProfile Menu:")
        print("  1. Edit User Info")
        print("  2. Show Won Bids")
        print("  3. Back to Main Menu")
        choice = input("Enter your choice: ")

        if choice == '1':
            edit_user_information()
            # After editing, refresh profile view if needed or rely on next explicit view
            view_profile() # Re-fetch and display updated profile
            break 
        elif choice == '2':
            show_won_bids()
        elif choice == '3':
            break
        else:
            print("Invalid choice. Please try again.")


def edit_user_information():
    global logged_in_user
    if not logged_in_user: return # Should not happen if called from view_profile

    print("\n--- Edit User Information ---")
    print("What would you like to edit?")
    print("  1. Username")
    print("  2. Email (Note: this might affect your login)")
    print("  3. Contact Address")
    print("  4. Password")
    print("  5. Add Balance")
    print("  6. Cancel")
    
    edit_choice = input("Enter your choice: ")
    field_to_edit = None
    new_value = None

    if edit_choice == '1':
        field_to_edit = "username"
        new_value = get_non_empty_input("Enter new username: ")
    elif edit_choice == '2':
        field_to_edit = "email"
        new_email = get_non_empty_input("Enter new email: ")
        if not is_valid_email_format(new_email):
            print("Invalid new email format.")
            return
        available = check_email_availability_on_server(new_email)
        if available is True:
            print("This email is already taken.")
            return
        elif available is None:
            print("Could not verify email availability. Edit aborted.")
            return
        new_value = new_email
    elif edit_choice == '3':
        field_to_edit = "contact"
        new_value = get_non_empty_input("Enter new contact address: ")
    elif edit_choice == '4':
        field_to_edit = "password"
        new_value = get_non_empty_input("Enter new password: ")
    elif edit_choice == '5':
        field_to_edit = "balance" # Server expects "balance" and a value to add
        try:
            amount_to_add_str = get_non_empty_input("Enter amount to add to balance: $")
            amount_to_add = int(amount_to_add_str)
            if amount_to_add < 0: # Or handle deposits only
                print("Cannot add a negative amount. Use withdraw feature if available.")
                return
            new_value = str(amount_to_add) # Server expects value as string for edit_info
        except ValueError:
            print("Invalid amount.")
            return
    elif edit_choice == '6':
        print("Edit cancelled.")
        return
    else:
        print("Invalid choice.")
        return

    if field_to_edit and new_value is not None:
        # User ID is needed by the server for edit_info
        response = execute_command(f"edit_info,{logged_in_user['id']},{field_to_edit},{new_value}")
        if response and response != "FAIL":
            try:
                updated_user_data = json.loads(response)
                # Update local logged_in_user with the new data from server
                # This is crucial because the server returns the complete updated user object
                logged_in_user = updated_user_data
                print(f"{field_to_edit.capitalize()} updated successfully.")
                if field_to_edit == "email" or field_to_edit == "password":
                    print("Note: If you changed your email or password, use the new credentials for your next login.")
            except json.JSONDecodeError:
                print("Update successful, but could not parse server response for local update.")
        else:
            print(f"Failed to update {field_to_edit}.")


def show_won_bids():
    global logged_in_user
    if not logged_in_user: return

    print("\n--- Your Won Bids ---")
    response = execute_command(f"won_bids,{logged_in_user['id']}")
    if not response:
        print("Could not fetch won bids.")
        return

    try:
        won_items = json.loads(response)
        if not won_items:
            print("You haven't won any bids yet.")
            return
        for item in won_items:
            print(f"\n  Title:       {item['title']}")
            print(f"  Description: {item.get('description', 'N/A')}")
            print(f"  Image URL:   {item.get('product_img', 'N/A')}")
            print(f"  Winning Price: ${item['last_price']:.2f}")
            print("  ----------------------------------")
    except json.JSONDecodeError:
        print("Error: Could not parse won bids data from server.")


# --- Main Application Loop ---
def main_menu_loop():
    global logged_in_user, client_socket, receive_thread, live_update_thread

    while not stop_event.is_set():
        print("\n++++++ Auction Management System ++++++")
        if logged_in_user:
            print(f"Logged in as: {logged_in_user.get('username')}")
        else:
            print("Status: Not logged in")
        
        print("---------------------------------------")
        print("| 1. Register User  | 2. Login          |")
        print("| 3. Create Auction | 4. View Auctions  |")
        print("| 5. Place Bid      | 6. Live Monitor   |")
        print("| 7. My Profile     | 8. Logout         |")
        print("| 9. Exit           |                   |")
        print("---------------------------------------")

        choice = input("Enter your choice: ").strip()

        if choice == '1':
            if logged_in_user: print("Please logout to register a new user.")
            else: register_user()
        elif choice == '2':
            if logged_in_user: print("You are already logged in.")
            else: login_user()
        elif choice == '3':
            if logged_in_user: create_new_auction()
            else: print("Please login to create an auction.")
        elif choice == '4':
            display_auctions()
        elif choice == '5':
            if logged_in_user: place_bid()
            else: print("Please login to place a bid.")
        elif choice == '6':
            if logged_in_user: manage_live_updates_session()
            else: print("Please login to use live auction monitoring.")
        elif choice == '7':
            if logged_in_user: view_profile()
            else: print("Please login to view your profile.")
        elif choice == '8':
            if logged_in_user: logout_user()
            else: print("You are not logged in.")
        elif choice == '9':
            print("Exiting Auction Management System. Goodbye!")
            stop_event.set() # Signal threads to stop
            break
        else:
            print("Invalid choice. Please enter a number between 1 and 9.")
        
        input("Press Enter to continue...") # Pause for readability

def main():
    global client_socket, receive_thread
    print("Starting Auction Client...")
    client_socket = connect_to_server(SERVER_HOST, SERVER_PORT)

    if client_socket:
        # Start the main message receiving thread once connection is established
        # This thread will run for the duration of the client's session.
        stop_event.clear()
        receive_thread = threading.Thread(target=receive_messages_loop, daemon=True)
        receive_thread.start()
        
        try:
            main_menu_loop()
        except KeyboardInterrupt:
            print("\nCtrl+C detected. Shutting down client...")
            stop_event.set()
        finally:
            if live_update_active_item_id and logged_in_user: # Stop active live monitor if any
                send_message(client_socket, f"stop_live_update,{live_update_active_item_id},{logged_in_user['id']}")

            print("Closing connection to server...")
            if client_socket:
                client_socket.close()
            
            if receive_thread and receive_thread.is_alive():
                receive_thread.join(timeout=2) # Wait for thread to finish
            
            print("Client shutdown complete.")
    else:
        print("Failed to connect to the server. Client will not start.")

if __name__ == '__main__':
    main()
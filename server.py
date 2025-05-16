import json
import os
import socket
import threading
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set

# Assuming a_server.py contains the Server class for client communication
from a_server import Server # Make sure a_server.py is in the same directory or Python path

# Constants for file names
USERS_FILE = 'users.txt'
AUCTIONS_FILE = 'auctions.txt'
BIDS_FILE = 'bids.txt'

# --- Database Initialization ---
def init_db():
    """Create empty JSON array files if they don't exist."""
    for file_name in [USERS_FILE, AUCTIONS_FILE, BIDS_FILE]:
        if not os.path.exists(file_name):
            with open(file_name, 'w') as file:
                json.dump([], file, indent=2)

# --- Data Models ---
class ClientModel:
    """
    Represents a client connected for live updates on a specific item.
    """
    def __init__(self, client_comm: Server, item_id: int, user_id: int):
        self.client_comm = client_comm
        self.item_id = item_id
        self.user_id = user_id

    def __eq__(self, other):
        if not isinstance(other, ClientModel):
            return NotImplemented
        # Uniquely identify by the underlying communication channel (socket)
        return self.client_comm.client.fileno() == other.client_comm.client.fileno()

    def __hash__(self):
        # Hash based on the underlying communication channel's file descriptor
        return hash(self.client_comm.client.fileno())

# --- Auction Server Class ---
class AuctionServer:
    def __init__(self, host='127.0.0.1', port=5561):
        self.host = host
        self.port = port
        self.clients_comm: List[Server] = []  # List of Server communication objects
        self.live_update_clients: Set[ClientModel] = set()

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.settimeout(5) # Timeout for accept
        self.server_socket.listen(5)

        self.update_item_queue = [] # Queue for broadcast messages
        self.data_lock = threading.Lock() # Lock for accessing shared data like files and client lists
        self.broadcast_lock = threading.Lock() # Lock for broadcasting operations

        self.running = True # Flag to control server loops

        print(f"[INFO] AuctionServer initialized. Files: {USERS_FILE}, {AUCTIONS_FILE}, {BIDS_FILE}")

    # --- Data Loading and Saving (Thread-Safe) ---
    def load_data(self, file_name: str) -> List[Dict[str, Any]]:
        with self.data_lock:
            if os.path.exists(file_name):
                try:
                    with open(file_name, 'r') as file:
                        return json.load(file)
                except json.JSONDecodeError:
                    print(f"[ERROR] Could not decode JSON from {file_name}. Returning empty list.")
                    return []
                except Exception as e:
                    print(f"[ERROR] Error loading data from {file_name}: {e}")
                    return []
            return []

    def save_data(self, file_name: str, data: List[Dict[str, Any]]) -> bool:
        with self.data_lock:
            try:
                with open(file_name, 'w') as file:
                    json.dump(data, file, indent=2)
                return True
            except Exception as e:
                print(f"[ERROR] Error saving data to {file_name}: {e}")
                return False

    # --- Broadcasting ---
    def broadcast_to_live_clients(self, message_info: Dict[str, Any]):
        """
        Broadcasts a message to relevant live update clients.
        message_info example: {"item_id": int, "user_id": int (optional), "msg": str, "type": "bid" | "live_check" | "winner"}
        """
        with self.broadcast_lock: # Ensure only one broadcast operation at a time
            # Create a copy for safe iteration, as live_update_clients might be modified
            clients_to_notify = list(self.live_update_clients)

        for client_model in clients_to_notify:
            try:
                # Send if the message is for the item this client is watching
                # Or if it's a general update not tied to a specific item (e.g. winner announcement for this client)
                should_send = False
                if message_info.get("type") == "winner_notification":
                    if client_model.user_id == message_info.get("user_id") and \
                       client_model.item_id == message_info.get("item_id"):
                        should_send = True
                elif message_info.get("item_id") == client_model.item_id :
                    should_send = True


                if should_send:
                    client_model.client_comm.send(message_info["msg"])

            except Exception as e:
                print(f"[ERROR] Failed to send live update to a client: {e}")
                self._remove_client(client_model.client_comm) # Remove problematic client

    def _remove_client(self, client_comm: Server):
        """Safely removes a client communication object and associated live update models."""
        with self.data_lock: # Protect shared client lists
            if client_comm in self.clients_comm:
                self.clients_comm.remove(client_comm)
                print(f"[INFO] Removed client communication: {client_comm.client.getpeername() if client_comm.client else 'unknown'}")

            # Remove any ClientModel instances associated with this client_comm
            # Create a list of items to remove to avoid modifying set during iteration
            to_remove_from_live = [cm for cm in self.live_update_clients if cm.client_comm == client_comm]
            for cm_to_remove in to_remove_from_live:
                self.live_update_clients.discard(cm_to_remove)
                print(f"[INFO] Removed client from live updates: user {cm_to_remove.user_id}, item {cm_to_remove.item_id}")


    # --- Client Handling ---
    def handle_client_connection(self, client_socket: socket.socket):
        client_address = client_socket.getpeername()
        print(f"[INFO] Accepted connection from {client_address}")
        client_comm = Server(client_socket) # Your encryption/decryption wrapper

        with self.data_lock:
            self.clients_comm.append(client_comm)

        try:
            while self.running:
                try:
                    data = client_comm.recv()
                    if not data:
                        print(f"[INFO] Client {client_address} disconnected (empty data).")
                        break
                    print(f"[RECV {client_address}] {data}")
                    self.process_command(client_comm, data)
                except ConnectionResetError:
                    print(f"[INFO] Client {client_address} reset the connection.")
                    break
                except socket.timeout: # If recv times out (if you set a timeout on client_socket)
                    continue # Or handle as needed
                except Exception as e:
                    print(f"[ERROR] Error handling client {client_address}: {e}")
                    # Consider sending an error message to the client if the connection is still up
                    # client_comm.send(json.dumps({"status": "error", "message": "Internal server error"}))
                    break
        finally:
            self._remove_client(client_comm)
            client_socket.close()
            print(f"[INFO] Closed connection for {client_address}")

    # --- Command Processing ---
    def process_command(self, client_comm: Server, command_str: str):
        parts = command_str.split(',', 3) # Split max 3 times for commands with more data
        cmd = parts[0]

        try:
            if cmd == 'login':
                _, email, password = command_str.split(',', 2)
             
                user = self._authenticate_user(email, password)
               
                client_comm.send(json.dumps(user) if user else "FAIL")
            elif cmd == "create_auction":
                _, title, description, img_url, base_price_str, end_time_str, seller_username = command_str.split(',', 6)
                auction_id = self._create_auction(title, description, img_url, int(base_price_str), end_time_str, seller_username)
                client_comm.send(str(auction_id) if auction_id else "FAIL")
            elif cmd == "won_bids":
                _, user_id_str = command_str.split(',', 1)
                items = self._get_won_items(int(user_id_str))
                client_comm.send(json.dumps(items))
            elif cmd == "edit_info":
                _, user_id_str, key, value = parts # command_str.split(',', 3)
                updated_user = self._edit_user_info(int(user_id_str), key, value)
                client_comm.send(json.dumps(updated_user) if updated_user else "FAIL")
            elif cmd == "check_item": # For non-live initial check
                _, auction_id_str = command_str.split(',', 1)
                response = self._get_auction_status_message(int(auction_id_str))
                client_comm.send(response)
            elif cmd == 'bid':
                _, user_id_str, item_id_str, bid_amount_str = command_str.split(',', 3)
                result = self._make_bid(client_comm, int(item_id_str), float(bid_amount_str), int(user_id_str))
                client_comm.send(result) # Sends "OK" or error message
            elif cmd == 'auction_list':
                ended_str = command_str.split(',')[1] if len(command_str.split(',')) > 1 else "0"
                ended = ended_str == "1"
                auctions = self._filter_auctions_by_status(ended)
                client_comm.send(json.dumps(auctions))
            elif cmd == 'live_auction': # Client wants to start receiving live updates for an auction
                _, item_id_str, user_id_str = command_str.split(',', 2)
                self._handle_live_subscription(client_comm, int(item_id_str), int(user_id_str))
            elif cmd == 'stop_live_update':
                _, item_id_str, user_id_str = command_str.split(',',2) # item_id might not be strictly needed if client_comm is unique
                self._handle_stop_live_subscription(client_comm, int(item_id_str), int(user_id_str))
            elif cmd == 'check_email':
                _, email = command_str.split(',', 1)
                user_exists = self._find_user_by_email(email) is not None
                client_comm.send("SUCCESS" if user_exists else "FAIL")
            elif cmd == 'add_user':
                # Expecting JSON string after "add_user-"
                try:
                    user_data_json = command_str.split(',', 1)[1]
                    user_data = json.loads(user_data_json) # Client should send valid JSON
                    success = self._add_new_user(user_data)
                    client_comm.send("SUCCESS" if success else "FAIL")
                except (IndexError, json.JSONDecodeError) as e:
                    print(f"[ERROR] Invalid add_user format or JSON: {e}")
                    client_comm.send("FAIL_FORMAT")
            else:
                client_comm.send('INVALID_COMMAND')
        except ValueError:
            client_comm.send("INVALID_COMMAND_ARGS")
            print(f"[ERROR] Value error processing command: {command_str}")
        except Exception as e:
            client_comm.send("SERVER_ERROR")
            print(f"[ERROR] Unexpected error processing command '{command_str}': {e}")


    # --- Auction Logic Implementation (Internal methods prefixed with _) ---
    def _authenticate_user(self, email: str, password_attempt: str) -> Optional[Dict[str, Any]]:
        user = self._find_user_by_email(email)
        if user and user.get("password") == password_attempt:
            return user
        return None

    def _find_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        users = self.load_data(USERS_FILE)
        for user in users:
            if user.get("email") == email:
                return user
        return None

    def _find_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        users = self.load_data(USERS_FILE)
        for user in users:
            if user.get("id") == user_id:
                return user
        return None

    def _find_auction_by_id(self, auction_id: int) -> Optional[Dict[str, Any]]:
        auctions = self.load_data(AUCTIONS_FILE)
        for auction in auctions:
            if auction.get("id") == auction_id:
                return auction
        return None

    def _create_auction(self, title: str, description: str, img_url: str, base_price: int, end_time_str: str, seller: str) -> Optional[int]:
        auctions = self.load_data(AUCTIONS_FILE)
        # Determine new ID: max existing ID + 1, or 1 if no auctions exist
        new_auction_id = (max(auction['id'] for auction in auctions) + 1) if auctions else 1

        new_auction = {
            'id': new_auction_id,
            'title': title,
            'description': description,
            'product_img': img_url,
            "base_price": base_price,
            'end_time': end_time_str, # Store as string, parse when needed
            'highest_bidder': None,
            'highest_bidder_id': None,
            'highest_bid': 0, # Or base_price initially if no bids yet and that's the logic
            'seller': seller,
            'status': 'active' # active, ended, sold
        }
        auctions.append(new_auction)
        if self.save_data(AUCTIONS_FILE, auctions):
            return new_auction_id
        return None

    def _get_won_items(self, user_id: int) -> List[Dict[str, Any]]:
        auctions = self.load_data(AUCTIONS_FILE)
        won_items = []
        for auction in auctions:
            if self._is_auction_ended(auction) and auction.get('highest_bidder_id') == user_id:
                item_summary = {
                    "id": auction['id'],
                    "title": auction['title'],
                    "description": auction['description'],
                    "product_img": auction['product_img'],
                    "last_price": auction['highest_bid']
                }
                won_items.append(item_summary)
        return won_items

    def _edit_user_info(self, user_id: int, key_to_edit: str, new_value: Any) -> Optional[Dict[str, Any]]:
        users = self.load_data(USERS_FILE)
        user_found = False
        updated_user_data = None
        for user in users:
            if user.get("id") == user_id:
                if key_to_edit == "balance":
                    try:
                        # Assuming new_value is the amount to add (or subtract if negative)
                        user["balance"] = user.get("balance", 0) + int(new_value)
                    except ValueError:
                        print(f"[ERROR] Invalid balance value for edit_info: {new_value}")
                        return None
                elif key_to_edit in user:
                    user[key_to_edit] = new_value
                else:
                    print(f"[WARN] Key '{key_to_edit}' not found for user {user_id} during edit.")
                    return None # Or handle as an error: key does not exist
                user_found = True
                updated_user_data = user
                break

        if user_found and self.save_data(USERS_FILE, users):
            return updated_user_data
        return None

    def _get_auction_status_message(self, auction_id: int, for_live_update=False) -> str:
        auction = self._find_auction_by_id(auction_id)
        if not auction:
            return "BAD_ID" if for_live_update else "Invalid auction ID."

        if self._is_auction_ended(auction):
            winner_msg = f"Winner: {auction.get('highest_bidder', 'N/A')}" if auction.get('highest_bidder') else "No bids."
            return f"AUCTION_ENDED,{auction_id},{auction.get('highest_bid', 0)},{winner_msg}"

        time_remaining_str = self.calculate_time_remaining_str(auction['end_time'])
        highest_bid = auction.get('highest_bid', 0)
        current_bid_info = f"Highest Bid: ${highest_bid} by {auction.get('highest_bidder', 'N/A')}" \
            if auction.get('highest_bidder') else f"Base Price: ${auction.get('base_price', 0)} by {auction.get('seller', 'System')}"

        if for_live_update:
            return f"LIVE_UPDATE,{auction_id},{time_remaining_str},{current_bid_info}"
        else:
            return f"Title: {auction['title']}\nTime Remaining: {time_remaining_str}\n{current_bid_info}"


    def _make_bid(self, client_comm: Server, auction_id: int, bid_amount: float, user_id: int) -> str:
        auctions = self.load_data(AUCTIONS_FILE) # Load fresh data
        users = self.load_data(USERS_FILE)       # Load fresh data

        auction_idx = next((i for i, auc in enumerate(auctions) if auc.get("id") == auction_id), -1)
        if auction_idx == -1:
            return "Invalid auction ID."

        auction = auctions[auction_idx]
        if self._is_auction_ended(auction):
            return "Bidding for this auction has ended."

        user_idx = next((i for i, usr in enumerate(users) if usr.get("id") == user_id), -1)
        if user_idx == -1:
            return "Invalid user ID."
        user = users[user_idx]

        current_highest_bid = float(auction.get('highest_bid', 0))
        effective_min_bid = float(auction.get('base_price', 0)) if current_highest_bid == 0 else current_highest_bid

        if bid_amount <= effective_min_bid:
            return f"You need to bid at least ${effective_min_bid + 0.01:.2f} to become the highest bidder."

        if bid_amount > user.get("balance", 0):
            return f"Not enough balance. Your balance: ${user.get('balance', 0):.2f}"

        # Update auction
        auction['highest_bid'] = bid_amount
        auction['highest_bidder'] = user.get("username", "Unknown User")
        auction['highest_bidder_id'] = user_id
        auctions[auction_idx] = auction # Ensure the list is updated with the modified dictionary

        # Record bid
        bids = self.load_data(BIDS_FILE)
        bids.append({
            'auction_id': auction_id,
            'bidder_id': user_id,
            'bidder_username': user.get("username"),
            'bid_amount': bid_amount,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        if self.save_data(AUCTIONS_FILE, auctions) and self.save_data(BIDS_FILE, bids):
            # Queue update for broadcast
            status_msg = self._get_auction_status_message(auction_id, for_live_update=True)
            with self.broadcast_lock:
                self.update_item_queue.append({
                    "item_id": auction_id,
                    "msg": status_msg,
                    "type": "bid"
                })
            return "OK"
        else:
            return "Failed to save bid. Please try again."

    def _filter_auctions_by_status(self, ended_status_requested: bool) -> List[Dict[str, Any]]:
        auctions = self.load_data(AUCTIONS_FILE)
        filtered = []
        for auction in auctions:
            is_ended = self._is_auction_ended(auction)
            if ended_status_requested and is_ended: # Requesting ended auctions, and it is ended
                filtered.append(auction)
            elif not ended_status_requested and not is_ended: # Requesting active auctions, and it is not ended
                filtered.append(auction)
        return filtered

    def _add_new_user(self, user_data: Dict[str, Any]) -> bool:
        users = self.load_data(USERS_FILE)
        if self._find_user_by_email(user_data.get("email", "")):
            print(f"[WARN] Attempt to add existing email: {user_data.get('email')}")
            return False # User with this email already exists

        new_user_id = (max(user['id'] for user in users) + 1) if users else 1
        new_user = {
            "id": new_user_id,
            "username": user_data.get("username"),
            "email": user_data.get("email"),
            "password": user_data.get("password"), # Consider hashing passwords
            "contact": user_data.get("contact"),
            "balance": float(user_data.get("balance", 0))
        }
        users.append(new_user)
        return self.save_data(USERS_FILE, users)

    def _is_auction_ended(self, auction: Dict[str, Any]) -> bool:
        if auction.get('status') == 'ended' or auction.get('status') == 'sold':
            return True
        try:
            end_time = datetime.strptime(auction['end_time'], '%Y-%m-%d %H:%M')
            return datetime.now() >= end_time
        except (ValueError, KeyError):
            print(f"[ERROR] Invalid end_time format or missing for auction ID {auction.get('id')}")
            return True # Treat as ended if time is invalid to prevent issues


    # --- Live Update Handling ---
    def _handle_live_subscription(self, client_comm: Server, item_id: int, user_id: int):
        auction = self._find_auction_by_id(item_id)
        if not auction:
            client_comm.send("INVALID_ID")
            return

        if self._is_auction_ended(auction):
            client_comm.send(self._get_auction_status_message(item_id))
            return

        new_client_model = ClientModel(client_comm, item_id, user_id)
        with self.data_lock: # Protect live_update_clients
             # Remove any old subscription from this client_comm before adding a new one
            to_remove = None
            for cm in self.live_update_clients:
                if cm.client_comm == new_client_model.client_comm : # Compare by client_comm (socket)
                    to_remove = cm
                    break
            if to_remove:
                self.live_update_clients.remove(to_remove)

            self.live_update_clients.add(new_client_model)

        print(f"[INFO] User {user_id} subscribed to live updates for item {item_id}. Total live clients: {len(self.live_update_clients)}")
        # Send initial status
        initial_status_msg = self._get_auction_status_message(item_id, for_live_update=True)
        client_comm.send(initial_status_msg)


    def _handle_stop_live_subscription(self, client_comm: Server, item_id: int, user_id: int):
        # Find the ClientModel instance associated with this client_comm
        client_to_remove = None
        with self.data_lock: # Protect live_update_clients
            for cm in self.live_update_clients:
                # Compare by the client_comm object itself or a unique identifier from it
                if cm.client_comm == client_comm and cm.item_id == item_id and cm.user_id == user_id:
                    client_to_remove = cm
                    break
            if client_to_remove:
                self.live_update_clients.discard(client_to_remove)
                client_comm.send(f"STOP_LIVE_UPDATE_CONFIRMED,{item_id}")
                print(f"[INFO] User {user_id} unsubscribed from item {item_id}. Remaining live: {len(self.live_update_clients)}")
            else:
                client_comm.send(f"NO_SUBSCRIPTION_FOUND,{item_id}")
                print(f"[WARN] No live subscription found to stop for user {user_id}, item {item_id}")

    # --- Background Tasks ---
    def broadcast_queued_updates_loop(self):
        """Periodically sends out queued updates."""
        while self.running:
            if self.update_item_queue:
                with self.broadcast_lock: # Ensure queue isn't modified while processing
                    message_info = self.update_item_queue.pop(0)
                self.broadcast_to_live_clients(message_info)
            time.sleep(0.1) # Short sleep to be responsive

    def check_ended_auctions_loop(self):
        """Periodically checks for auctions that have ended."""
        while self.running:
            auctions = self.load_data(AUCTIONS_FILE)
            users = self.load_data(USERS_FILE) # Load once per check
            updated_auctions = False

            for i, auction in enumerate(auctions):
                if auction.get('status') == 'active' and self._is_auction_ended(auction):
                    auctions[i]['status'] = 'ended' # Mark as ended
                    updated_auctions = True
                    winner_id = auction.get('highest_bidder_id')
                    auction_id = auction.get('id')

                    print(f"[INFO] Auction ID {auction_id} has ended.")

                    if winner_id is not None:
                        auctions[i]['status'] = 'sold'
                        # Find winner to deduct balance
                        winner_user_idx = next((idx for idx, u in enumerate(users) if u.get("id") == winner_id), -1)
                        if winner_user_idx != -1:
                            users[winner_user_idx]['balance'] = users[winner_user_idx].get('balance', 0) - auction.get('highest_bid', 0)
                            print(f"[INFO] User ID {winner_id} won auction {auction_id}. Balance updated.")
                        else:
                            print(f"[ERROR] Winner ID {winner_id} not found for auction {auction_id} to update balance.")

                        # Notify winner (and potentially other bidders on this item)
                        winner_msg = f"WINNER_NOTIFICATION,{auction_id},Congratulations! You won item {auction['title']} for ${auction['highest_bid']}."
                        loser_msg = f"AUCTION_ENDED,{auction_id},Item {auction['title']} was sold to {auction.get('highest_bidder')} for ${auction['highest_bid']}."

                        with self.broadcast_lock: # Queue messages
                            self.update_item_queue.append({
                                "item_id": auction_id,
                                "user_id": winner_id, # Specific user for this message
                                "msg": winner_msg,
                                "type": "winner_notification"
                            })
                            # For other live clients watching this item
                            self.update_item_queue.append({
                                "item_id": auction_id,
                                "msg": loser_msg, # Generic ended message for others
                                "type": "auction_end_general"
                            })
                    else: # No winner
                        no_bid_msg = f"AUCTION_ENDED,{auction_id},Item {auction['title']} ended with no bids."
                        with self.broadcast_lock:
                             self.update_item_queue.append({
                                "item_id": auction_id,
                                "msg": no_bid_msg,
                                "type": "auction_end_general"
                            })


            if updated_auctions:
                self.save_data(AUCTIONS_FILE, auctions)
                if any(auction.get('status') == 'sold' for auction in auctions): # Only save users if a sale happened
                    self.save_data(USERS_FILE, users)

            time.sleep(5) # Check every 5 seconds


    @staticmethod
    def calculate_time_remaining_str(end_time_str: str) -> str:
        try:
            end_time = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M')
            time_remaining = end_time - datetime.now()
            if time_remaining.total_seconds() <= 0:
                return "Ended"
            days, seconds = divmod(int(time_remaining.total_seconds()), 86400)
            hours, seconds = divmod(seconds, 3600)
            minutes, seconds = divmod(seconds, 60)
            return f"{days}d {hours}h {minutes}m {seconds}s"
        except ValueError:
            return "Invalid time format"

    # --- Server Start and Stop ---
    def start(self):
        init_db() # Ensure files exist
        print(f'[INFO] Server listening on {self.host}:{self.port}...')
        self.running = True

        self.broadcast_thread = threading.Thread(target=self.broadcast_queued_updates_loop, daemon=True)
        self.auction_check_thread = threading.Thread(target=self.check_ended_auctions_loop, daemon=True)

        self.broadcast_thread.start()
        self.auction_check_thread.start()

        try:
            while self.running:
                try:
                    client_socket, _ = self.server_socket.accept() # Timeout is set on server_socket
                    handler_thread = threading.Thread(target=self.handle_client_connection, args=(client_socket,), daemon=True)
                    handler_thread.start()
                except socket.timeout:
                    continue # Just loop again to check self.running
                except OSError as e: # Handle server socket being closed if self.running is set to False
                    if self.running:
                        print(f"[ERROR] Server socket error: {e}")
                    break # Exit loop if socket error and not explicitly running
        except KeyboardInterrupt:
            print("[INFO] Server shutting down due to KeyboardInterrupt...")
        finally:
            self.shutdown()

    def shutdown(self):
        print("[INFO] Initiating server shutdown...")
        self.running = False
        # Close client connections
        with self.data_lock: # Use lock when accessing clients_comm
            for client_comm in list(self.clients_comm): # Iterate over a copy
                try:
                    # Optionally send a shutdown message
                    # client_comm.send(json.dumps({"status": "shutdown", "message": "Server is shutting down."}))
                    client_comm.client.close()
                except Exception as e:
                    print(f"[WARN] Error closing a client socket during shutdown: {e}")
            self.clients_comm.clear()
            self.live_update_clients.clear()

        if self.server_socket:
            self.server_socket.close()
            print("[INFO] Server socket closed.")

        if hasattr(self, 'broadcast_thread') and self.broadcast_thread.is_alive():
            self.broadcast_thread.join(timeout=1)
        if hasattr(self, 'auction_check_thread') and self.auction_check_thread.is_alive():
            self.auction_check_thread.join(timeout=1)

        print("[INFO] Server has been shut down.")

# --- Main Execution ---
if __name__ == "__main__":
    server = AuctionServer()
    server.start()
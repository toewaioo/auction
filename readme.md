# Auction Management System

This project implements a client-server application for an auction management system, including user registration, login, creating auctions, placing bids, viewing auction lists, and live updates. It also incorporates a custom encryption scheme for communication.

## Features

* **User Management:** Register new users and log in existing ones. [cite: 168, 169]
* **Auction Creation:** Logged-in users can create new auction items with a title, description, image URL, base price, and end time. [cite: 177]
* **Bidding:** Logged-in users can place bids on active auction items. [cite: 170]
* **Auction Listings:** View lists of active and ended auctions. [cite: 45, 173]
* **Live Updates:** Monitor the status of specific auction items in near real-time. [cite: 27, 28, 174, 280]
* **Profile Management:** View and edit user information (username, email, contact, balance) and see won bids. [cite: 42, 43, 59, 175, 176, 301]
* **Custom Encryption:** Communication between the client and server is encrypted using a custom XOR-based scheme. [cite: 111, 182, 184, 192, 194]

## Code Structure

The project consists of the following main files:

* `server.py`: Contains the core `AuctionServer` class, handling client connections[cite: 34], command processing[cite: 39], data loading/saving[cite: 22, 24, 25], broadcasting[cite: 26, 28], and auction logic[cite: 51]. It also incorporates the server-side communication/encryption logic (originally in `a_server.py`)[cite: 16, 110].
* `client.py`: Implements the client-side application with a command-line interface for user interaction[cite: 179], including connecting to the server[cite: 241], sending commands[cite: 248], receiving responses[cite: 243], and managing live updates[cite: 280].
* `encrypt_decrypt.py`: Provides the `A3Encryption` [cite: 182] and `A3Decryption` [cite: 192] classes for the custom encryption and decryption logic used for client-server communication.

## Setup and Installation

1.  **Clone the repository** (assuming the code is in a repository).
2.  **Ensure Python 3 is installed.**
3.  Place `server.py`, `client.py`, and `encrypt_decrypt.py` in the same directory.
4.  Ensure the data files (`users.txt`, `auctions.txt`, `bids.txt`) are present in the same directory as `server.py`. The server will initialize them as empty JSON arrays if they don't exist. [cite: 17]

## How to Run

1.  **Start the server:** Open a terminal or command prompt, navigate to the project directory, and run:
    ```bash
    python server.py
    ```
    The server should indicate that it's listening on the configured host and port (default: `127.0.0.1:5555`). [cite: 20, 103, 352]
2.  **Start the client:** Open another terminal or command prompt, navigate to the project directory, and run:
    ```bash
    python client.py
    ```
    The client should connect to the server [cite: 319] and present the main menu[cite: 179].

## Custom Encryption

The project uses a custom encryption scheme based on XOR operations with a total key (derived from a shared string) and a random key (unique per connection and sent with the payload). [cite: 111, 182, 184, 192, 194, 229, 230, 232, 233]

**Note:** While a custom scheme is implemented, it is strongly recommended to use well-vetted, standard cryptographic libraries for security in production environments, as custom schemes are hard to get right and can have vulnerabilities. [cite: 111, 164] The current implementation's handling of values exceeding 16 bits during encryption might lead to potential information loss for certain Unicode characters. [cite: 392]

## Areas for Potential Improvement

Based on the code analysis, the following areas could be further improved:

* **Security:** Use standard cryptographic libraries instead of the custom scheme. [cite: 111, 164] Implement secure password hashing. [cite: 76]
* **Networking Robustness:** Implement a message framing protocol (e.g., length prefixing) for more robust TCP communication to handle messages larger than the buffer size and ensure complete messages are received. [cite: 15, 161]
* **Thread Safety:** Ensure consistent use of locks for all access to shared resources and collections. [cite: 6, 21, 32, 135]
* **Error Handling:** Implement more specific and robust error handling on both the client and server sides. [cite: 4, 23, 24, 25, 38, 49, 50, 160, 211, 213, 246, 247, 335]
* **Input Validation:** Stricter validation of inputs from clients. [cite: 7]
* **Concurrency:** Explore more event-driven approaches for broadcasting instead of polling. [cite: 7]
* **Code Structure:** Further modularize code [cite: 3] and improve adherence to PEP 8 standards. [cite: 2] Add more comprehensive docstrings and comments. [cite: 3]
* **Client UI:** Improve user experience and input validation in the client application. [cite: 213] Refine live update handling for better user feedback.
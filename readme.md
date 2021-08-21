# Akrios-II Front End

Akrios-II is a Multi-User Dungeon(MUD) written entirely in Python 3.  **This** project is the front end for Akrios-II which
accepts Telnet, "Secure Telnet", and SSH connections for client connectivity and provides communication to the mud engine via JSON over websockets.  This fron end  also provides MSSP protocol for clients and "MUD Crawlers".  

The front end is built using the Python asyncio module and aims to be concurrent. Both Akrios-II and this front end require Python 3.10+.

All testing, to date, is performed using the Mudlet MUD client.



## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### First

Clone this repo!

### Requirements

The Akrios-II Front End has several requirements which are not part of the standard library.  You will need to install those dependencies prior to running this package.  Your exact Python setup will determine the correct procedure to install them.  The below is a generic example.

```
pip3 install -r requirements.txt
```

### Create SSH key and Secret for Websocket Communications

There are three steps you need to complete prior to running the front end.  

First, a local SSH key will need to be created, named 'akrios_ca', for client SSH connectivity.  You should use a passphrase when creating the key.

```
ssh-keygen -t rsa -b 4096 -o -a 100
```

Second a certificate and key will need to be created for the client "Secure Telnet" SSL/TLS context.

```
openssl req -newkey rsa:2048 -new -nodes -x509 -days 3650 -keyout server_key.pem -out server_cert.pem
```

Third, you will need to create a websocket secret key to use between the front end and the game engine as well as provide the passphrase you used during SSH keygen.  Create a keys.py with the following information.

```
WS_SECRET = ""     <- This can be anything, I use a uuid4 (Needs to match MUD Engine)
passphrase = ""    <- This needs to be the phrase you used during SSH keygen.
```

It would be trivial to modify this package to pull these values out of environment variables.  That is left as an exercise for the reader.


## Caveats

The Akrios-II engine has a softboot type capability. Please review parse.py in this package and update the softboot section accordingly.

The starting point for launching this front end is **frontend.py**
## Finally

This, being a front end, will need a game engine to communicate with.  Currently this project is specific to [Akrios-II](https://github.com/bdubyapee/akrios-ii) which is my pure Python, 100% custom, engine.  This front end can be adapted to any other MU* which could be written to communicate with this front end via websockets.

## Authors

* **Jubelo**


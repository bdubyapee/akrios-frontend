# Akrios-II Front End

Akrios-II is a Multi-User Dungeon(MUD) written entirely in Python 3.  **This** project is the front end for Akrios-II which
accepts Telnet and SSH connections and facilitates input/output between the MUD engine and clients.  The front end is built using the Python asyncio module and aims to be concurrent. Both Akrios-II and this Front End require Python 3.8+.



## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Step One

Clone this repo!

### Requirements

The Akrios-II Front End has several requirements which are not part of the standard library.  You will need to install those dependencies prior to running this package.  Your exact Python setup will determine the correct procedure to install them.  The below is a generic example.

```
pip3 install -r requirements.txt
```

### Installing

There are two steps you need to complete prior to running the front end.  

A local SSH key will need to be created, named 'akrios_ca', for that portion of the connectivity.  You should use a passphrase when creating the key.

```
ssh-keygen -t rsa -b 4096 -o -a 100
```

You will need to create a websocket secret key to use between the front end and the game engine as well as provide the passphrase you used during SSH keygen.  Create a keys.py with the following information.

```
WS_SECRET = ""     <- This can be anything, I use a uuid4 (Needs to match MUD Engine)
passphrase = ""    <- This needs to be the phrase you used during SSH keygen.
```

It would be trivial to modify this package to pull these values out of environment variables.  That is left as an exercise for the reader.


## Deployment

This, being a front end, will need a game engine to communicate with.  Currently this project is specific to [Akrios-II](https://github.com/bdubyapee/akrios-ii) which is my pure Python, 100% custom, engine.  This front end can be adapted to any other MU* which could be written to communicate with this front end via websockets.

## Authors

* **Jubelo**


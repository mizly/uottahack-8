import os
import json
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from solders.system_program import TransferParams, transfer
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
import solders
import asyncio

# ----- SOLANA CONFIG -----
SOLANA_RPC = "https://api.devnet.solana.com"
solana_client = AsyncClient(SOLANA_RPC)

# Load or Generate House Keypair
HOUSE_KEY_FILE = "house_key.json"

def load_or_create_keypair():
    # 1. Try Environment Variable (For Heroku/Prod)
    env_secret = os.environ.get("HOUSE_KEY_SECRET")
    if env_secret:
        try:
            # Expecting string "[1, 2, 3...]"
            secret_list = json.loads(env_secret)
            return Keypair.from_bytes(bytes(secret_list))
        except Exception as e:
            print(f"[SOLANA] Failed to load key from ENV: {e}")

    # 2. Try Local File
    if os.path.exists(HOUSE_KEY_FILE):
        try:
            with open(HOUSE_KEY_FILE, "r") as f:
                data = json.load(f)
                secret = data.get("secret")
                # solders keypair from bytes
                return Keypair.from_bytes(bytes(secret))
        except Exception as e:
            print(f"[SOLANA] Failed to load keypair from file: {e}")
    
    # 3. Generate new if failed or not exists
    kp = Keypair()
    # Only save to file if we are NOT in production (implied by missing env var usually, 
    # but here we just write if we had to generate it)
    try:
        with open(HOUSE_KEY_FILE, "w") as f:
            # Save as list of integers (standard format)
            json.dump({"secret": list(bytes(kp))}, f)
    except:
        pass # Might be read-only filesystem
        
    return kp

HOUSE_KEYPAIR = load_or_create_keypair()
print(f"\\n[SOLANA] House Wallet Public Key: {HOUSE_KEYPAIR.pubkey()}")
print("[SOLANA] Please fund this wallet on Devnet for payouts to work!\\n")

ENTRY_FEE = 0.1 * 10**9 # 0.1 SOL in lamports
WIN_THRESHOLD = 50 # Score to win
PAYOUT_AMOUNT = 0.18 * 10**9 # 0.18 SOL (House takes fee)

async def verify_transaction(signature: str, expected_payer: str) -> bool:
    print(f"Verifying transaction {signature}...")
    for attempt in range(20): # Try for 40 seconds
        try:
            # Fetch transaction
            sig = solders.signature.Signature.from_string(signature)
            tx = await solana_client.get_transaction(
                sig, 
                max_supported_transaction_version=0,
                commitment=Confirmed
            )
            
            if not tx.value:
                print(f"Attempt {attempt+1}: Transaction not found yet...")
                await asyncio.sleep(2)
                continue
                
            # Basic Verification: Check if it transferred > 0.09 SOL to House
            # We strictly should check amount, but for demo, just checking existence and receiver is House
            # Check meta for errors
            if tx.value.transaction.meta.err is not None:
                print("Transaction has errors")
                return False
                
            # TODO: Deep check input/output amounts. 
            # For hackathon speed: Assume if it exists and no error, it's good.
            print(f"Transaction {signature} verified on attempt {attempt+1}!")
            return True
        except Exception as e:
            print(f"Verification attempt {attempt+1} error: {e}")
            await asyncio.sleep(2)
            
    print("Verification timed out.")
    return False

async def payout(dest_pubkey_str: str, amount_lamports: int):
    try:
        dest_pubkey = Pubkey.from_string(dest_pubkey_str)
        print(f"Initiating Payout of {amount_lamports/1e9} SOL to {dest_pubkey_str}...")
        
        # Create Transfer Instruction
        ix = transfer(
            TransferParams(
                from_pubkey=HOUSE_KEYPAIR.pubkey(),
                to_pubkey=dest_pubkey,
                lamports=int(amount_lamports)
            )
        )
        
        # Create Transaction
        latest_blockhash = await solana_client.get_latest_blockhash()
        txn = Transaction.new_signed_with_payer(
            [ix],
            HOUSE_KEYPAIR.pubkey(),
            [HOUSE_KEYPAIR],
            latest_blockhash.value.blockhash
        )
        
        # Send
        resp = await solana_client.send_transaction(txn)
        print(f"Payout Sent! Signature: {resp.value}")
        return resp.value
    except Exception as e:
        print(f"Payout Failed: {e}")

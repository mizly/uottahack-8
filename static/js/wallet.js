// Returns signature on success, throws on failure
export async function processTransaction() {
    if (!userWallet) {
        throw new Error("Wallet not connected");
    }

    // Create Transaction
    const connection = new solanaWeb3.Connection(solanaWeb3.clusterApiUrl('devnet'), 'confirmed');

    if (!housePublicKey) {
        throw new Error("Server wallet address missing. Refresh.");
    }

    const transaction = new solanaWeb3.Transaction().add(
        solanaWeb3.SystemProgram.transfer({
            fromPubkey: userWallet,
            toPubkey: new solanaWeb3.PublicKey(housePublicKey),
            lamports: 0.1 * solanaWeb3.LAMPORTS_PER_SOL // 0.1 SOL Entry
        })
    );

    const { blockhash } = await connection.getLatestBlockhash();
    transaction.recentBlockhash = blockhash;
    transaction.feePayer = userWallet;

    // Sign and Send (Wallet Adapter Only)
    const { signature } = await window.solana.signAndSendTransaction(transaction);
    console.log("Transaction Sent:", signature);

    // Wait for brief propagation
    await new Promise(resolve => setTimeout(resolve, 2000));
    refreshBalance();

    return signature;
}

let userWallet = null; // Public Key Object
let housePublicKey = null;

// Fetch House Key
fetch('/house-key').then(r => r.json()).then(data => {
    housePublicKey = data.publicKey;
    console.log("House Wallet:", housePublicKey);
}).catch(e => console.log("House key fetch failed"));

const getProvider = () => {
    if ('phantom' in window) {
        const provider = window.phantom?.solana;

        if (provider?.isPhantom) {
            return provider;
        }
    }

    // Fallback to standard window.solana
    if (window.solana?.isPhantom) {
        return window.solana;
    }

    return null;
};

export async function connectWallet() {
    const provider = getProvider();

    if (provider) {
        try {
            const resp = await provider.connect();
            userWallet = resp.publicKey;

            // Update UI
            updateWalletUI(userWallet.toString());
            refreshBalance();
        } catch (err) {
            console.error("Wallet connection error:", err);

            // Handle specific extension error
            if (err.message && err.message.includes("disconnected port")) {
                alert("Phantom Wallet extension disconnected. Please refresh the page and try again.");
            } else {
                // User rejected or other error
                console.log("Connection request rejected or failed.");
            }
        }
    } else {
        window.open("https://phantom.app/", "_blank");
    }
}

export async function refreshBalance() {
    if (!userWallet) return;
    try {
        const connection = new solanaWeb3.Connection(solanaWeb3.clusterApiUrl('devnet'), 'confirmed');
        const balance = await connection.getBalance(userWallet);
        const sol = (balance / solanaWeb3.LAMPORTS_PER_SOL).toFixed(2);

        updateWalletUI(userWallet.toString(), sol);
    } catch (e) {
        console.error("Failed to fetch balance", e);
    }
}

function updateWalletUI(addressStr, balanceSol = null) {
    const walletText = document.getElementById('wallet-text');
    const indicator = document.getElementById('wallet-indicator');

    const addr = addressStr.slice(0, 4) + '...' + addressStr.slice(-4);
    if (balanceSol !== null && walletText) {
        walletText.textContent = `${addr} (${balanceSol} SOL)`;
    } else if (walletText) {
        walletText.textContent = addr;
    }

    if (indicator) {
        indicator.className = "w-2 h-2 rounded-full bg-ios-green shadow-[0_0_8px_rgba(48,209,88,1)]";
    }
}

export function getUserWallet() {
    return userWallet;
}

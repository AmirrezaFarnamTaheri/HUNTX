// Web Worker for high-throughput WebAssembly proxy decoding and decompression.
//
// Every inbound message is answered exactly once. A request that goes
// unanswered leaves the caller's promise pending forever, so the unknown-action
// and not-ready paths both reply rather than returning silently.
importScripts('./wasm_exec.js');

/** @type {'pending' | 'ready' | 'failed'} */
let wasmState = 'pending';
let wasmError = '';

const go = new Go();

WebAssembly.instantiateStreaming(fetch('../huntx_engine.wasm'), go.importObject)
    .then((result) => {
        // go.run resolves only when the Go program exits, so it is deliberately
        // not awaited. It registers the exported decode function synchronously.
        go.run(result.instance);
        wasmState = 'ready';
        self.postMessage({ type: 'WASM_INITIALIZED' });
    })
    .catch((err) => {
        wasmState = 'failed';
        wasmError = (err && err.message) || String(err);
        self.postMessage({ type: 'WASM_INIT_ERROR', error: wasmError });
    });

function decoderUnavailableReason() {
    if (wasmState === 'failed') {
        return `Wasm module failed to initialize: ${wasmError}`;
    }
    if (wasmState === 'pending') {
        return 'Wasm decoder is still initializing';
    }
    // Ready, but the module did not export what we expect.
    return 'Wasm decoder function is not exported by the loaded module';
}

self.onmessage = function (e) {
    const { action, payload, id } = e.data || {};

    if (action !== 'DECODE_SUBSCRIPTION') {
        self.postMessage({
            id,
            type: 'DECODE_ERROR',
            error: `Unsupported worker action: ${String(action)}`,
        });
        return;
    }

    if (wasmState !== 'ready' || typeof huntx_decode_subscription !== 'function') {
        self.postMessage({ id, type: 'DECODE_ERROR', error: decoderUnavailableReason() });
        return;
    }

    try {
        self.postMessage({ id, type: 'DECODE_RESULT', data: huntx_decode_subscription(payload) });
    } catch (err) {
        self.postMessage({ id, type: 'DECODE_ERROR', error: (err && err.message) || String(err) });
    }
};

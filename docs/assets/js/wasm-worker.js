// Web Worker for high-throughput WebAssembly proxy decoding and decompression
importScripts('./wasm_exec.js');

let wasmLoaded = false;
const go = new Go();

WebAssembly.instantiateStreaming(fetch('../huntx_engine.wasm'), go.importObject)
    .then((result) => {
        go.run(result.instance);
        wasmLoaded = true;
        self.postMessage({ type: 'WASM_INITIALIZED' });
    })
    .catch((err) => {
        self.postMessage({ type: 'WASM_INIT_ERROR', error: err.message });
    });

self.onmessage = function (e) {
    const { action, payload, id } = e.data || {};
    if (action === 'DECODE_SUBSCRIPTION') {
        if (typeof huntx_decode_subscription === 'function') {
            try {
                const res = huntx_decode_subscription(payload);
                self.postMessage({ id, type: 'DECODE_RESULT', data: res });
            } catch (err) {
                self.postMessage({ id, type: 'DECODE_ERROR', error: err.message });
            }
        } else {
            self.postMessage({ id, type: 'DECODE_ERROR', error: 'Wasm decoder function not ready' });
        }
    }
};

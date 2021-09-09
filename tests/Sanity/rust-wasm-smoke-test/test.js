function js_fibonacci(index) {
    let nminus2 = 0;
    let nminus1 = 1;
    let n = 0;
    for(let i = 0; i < index; ++i) {
        nminus2 = nminus1;
        nminus1 = n;
        n = nminus1 + nminus2;
    }
    return n;
}

const fs = require('fs');
const buf = fs.readFileSync('./fib.wasm');
const lib = WebAssembly.instantiate(new Uint8Array(buf)).
    then(res => {
        var fib = res.instance.exports.fib;
        for (var i=1; i<=10; i++) {
            if(fib(i) != js_fibonacci(i)){
                console.log("Mismatch between wasm and JS functions");
                process.exit(1);
            }
        }
    }).catch(e => {
        console.log(e);
        process.exit(1);
    }
);

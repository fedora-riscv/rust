#[no_mangle]
pub fn fib(index: u32) -> u32 {
    let mut nminus2;
    let mut nminus1 = 1;
    let mut n = 0;
    for _ in 0..index {
        nminus2 = nminus1;
        nminus1 = n;
        n = nminus2 + nminus1;
    }
    n
}

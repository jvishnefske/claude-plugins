---
description: Use this skill when the user needs guidance on safe Rust patterns, newtype wrappers, type-state machines, error handling, no-panic code, Kani harnesses, or Clippy configuration for production-grade development.
---

# Safe Rust Patterns Skill

This skill provides patterns for writing production-grade Rust code that passes all verification layers.

## Core Principles

1. **Make illegal states unrepresentable**
2. **Make illegal operations uncompilable**
3. **Fail at compile time, not runtime**
4. **No panics in production code**
5. **Explicit is better than implicit**

## Pattern 1: Newtype Wrappers

Prevent type confusion with newtypes:

```rust
/// Speed in RPM - always valid
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Rpm(u16);

impl Rpm {
    pub const ZERO: Self = Self(0);
    pub const MAX: Self = Self(5000);

    /// Fallible construction
    pub const fn new(value: u16) -> Option<Self> {
        if value <= 5000 { Some(Self(value)) } else { None }
    }

    /// Infallible construction (saturates)
    pub const fn saturating_new(value: u16) -> Self {
        if value <= 5000 { Self(value) } else { Self::MAX }
    }

    /// Safe accessor
    pub const fn get(self) -> u16 { self.0 }

    /// Checked arithmetic
    pub const fn checked_add(self, rhs: Self) -> Option<Self> {
        match self.0.checked_add(rhs.0) {
            Some(v) if v <= 5000 => Some(Self(v)),
            _ => None,
        }
    }
}
```

## Pattern 2: Type-State Machines

Compile-time state transition enforcement:

```rust
use core::marker::PhantomData;

// State markers (zero-sized types)
pub struct Idle;
pub struct Running;
pub struct Fault;

pub struct Motor<State> {
    pwm: PwmChannel,
    _state: PhantomData<State>,
}

// Only valid transitions compile
impl Motor<Idle> {
    pub fn start(self) -> Motor<Running> {
        Motor { pwm: self.pwm, _state: PhantomData }
    }
}

impl Motor<Running> {
    pub fn stop(self) -> Motor<Idle> {
        Motor { pwm: self.pwm, _state: PhantomData }
    }

    pub fn fault(self) -> Motor<Fault> {
        Motor { pwm: self.pwm, _state: PhantomData }
    }
}

// COMPILE ERROR: motor.start().start() - can't start Running
```

## Pattern 3: Error Types with Context

Rich error types for debugging:

```rust
#[derive(Debug)]
pub enum MotorError {
    SpeedExceedsLimit { commanded: Rpm, limit: Rpm },
    Timeout { elapsed_ms: u32, threshold_ms: u32 },
    HardwareFault(FaultCode),
}

impl MotorError {
    pub const fn is_critical(&self) -> bool {
        matches!(self, Self::HardwareFault(_))
    }
}
```

## Pattern 4: Bounded Collections

No heap allocation:

```rust
use heapless::Vec;

pub struct EventLog {
    events: Vec<Event, 64>,  // Max 64 events, stack allocated
}

impl EventLog {
    pub fn push(&mut self, event: Event) -> Result<(), BufferFull> {
        self.events.push(event).map_err(|_| BufferFull)
    }
}
```

## Pattern 5: No Panic Arithmetic

```rust
// BAD
fn bad_add(a: u32, b: u32) -> u32 {
    a + b  // Panics on overflow in debug
}

// GOOD
fn checked_add(a: u32, b: u32) -> Option<u32> {
    a.checked_add(b)
}

fn saturating_add(a: u32, b: u32) -> u32 {
    a.saturating_add(b)
}
```

## Pattern 6: No Index Panics

```rust
// BAD
fn bad_get(slice: &[u8], i: usize) -> u8 {
    slice[i]  // Panics if out of bounds
}

// GOOD
fn safe_get(slice: &[u8], i: usize) -> Option<u8> {
    slice.get(i).copied()
}
```

## Pattern 7: Result Everywhere

```rust
// BAD
fn bad_parse(s: &str) -> u32 {
    s.parse().unwrap()  // Panics
}

// GOOD
fn safe_parse(s: &str) -> Result<u32, ParseError> {
    s.parse().map_err(|_| ParseError)
}
```

## Pattern 8: Minimal Unsafe

```rust
/// SAFETY: Document all invariants
///
/// # Safety
/// - `addr` must be valid peripheral base address
/// - Must be called only once per peripheral
pub unsafe fn init_peripheral(addr: usize) -> Peripheral {
    // SAFETY: Caller guarantees addr validity
    let regs = &*(addr as *const Registers);
    Peripheral { regs }
}

// Wrap in safe API
pub fn get_peripheral() -> Peripheral {
    static INIT: Once<Peripheral> = Once::new();
    *INIT.call_once(|| {
        // SAFETY: PERIPHERAL_ADDR is linker-provided, only called once
        unsafe { init_peripheral(PERIPHERAL_ADDR) }
    })
}
```

## Pattern 9: Kani Harnesses

```rust
#[cfg(kani)]
mod verification {
    use super::*;

    #[kani::proof]
    fn verify_rpm_bounded() {
        let v: u16 = kani::any();
        let rpm = Rpm::saturating_new(v);
        assert!(rpm.get() <= 5000);
    }

    #[kani::proof]
    #[kani::unwind(5)]
    fn verify_no_overflow() {
        let a: u16 = kani::any();
        let b: u16 = kani::any();
        kani::assume(a <= 5000 && b <= 5000);

        if let Some(rpm_a) = Rpm::new(a) {
            if let Some(rpm_b) = Rpm::new(b) {
                // This should never panic
                let _ = rpm_a.checked_add(rpm_b);
            }
        }
    }
}
```

## Pattern 10: Clippy Configuration

```toml
# Cargo.toml
[lints.clippy]
unwrap_used = "deny"
expect_used = "deny"
panic = "deny"
todo = "deny"
unimplemented = "deny"
indexing_slicing = "deny"
pedantic = { level = "warn", priority = -1 }
```

## Crate Attributes

```rust
// lib.rs
#![no_std]
#![deny(unsafe_code)]  // Opt-in to unsafe
#![deny(clippy::unwrap_used)]
#![deny(clippy::panic)]
#![warn(clippy::pedantic)]
#![warn(missing_docs)]
```

## Testing Patterns

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    proptest! {
        #[test]
        fn rpm_always_valid(v in 0u16..=10000) {
            let rpm = Rpm::saturating_new(v);
            prop_assert!(rpm.get() <= 5000);
        }
    }
}
```

## Dependency Selection

Prefer these safety-oriented crates:

| Need | Crate | Why |
|------|-------|-----|
| Collections | `heapless` | No heap, bounded |
| HAL | `embedded-hal` | Standard traits |
| Errors | `defmt` | Efficient logging |
| Sync | `critical-section` | Platform-agnostic |
| Time | `fugit` | Compile-time units |

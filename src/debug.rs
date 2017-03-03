#[derive(Clone, Copy)]
pub enum DebugUtf8<'a>{
    ValidUtf8(&'a str),
    InvalidUtf8(&'a [u8]),
}

pub fn debug_utf8<'a>(s: &'a [u8]) -> DebugUtf8<'a> {
    match ::std::str::from_utf8(s) {
        Ok(s) => DebugUtf8::ValidUtf8(s),
        Err(_) => DebugUtf8::InvalidUtf8(s),
    }
}

impl<'a> ::std::fmt::Debug for DebugUtf8<'a> {
    fn fmt(&self, f: &mut ::std::fmt::Formatter) -> ::std::fmt::Result {
        match self {
            &DebugUtf8::ValidUtf8(s) => write!(f, "b{:?}", s),
            &DebugUtf8::InvalidUtf8(s) => s.fmt(f),
        }
    }
}

impl<'a> ::std::fmt::Display for DebugUtf8<'a> {
    fn fmt(&self, f: &mut ::std::fmt::Formatter) -> ::std::fmt::Result {
        match self {
            &DebugUtf8::ValidUtf8(s) => write!(f, "{}", s),
            &DebugUtf8::InvalidUtf8(s) => {
                for c in s {
                    try!(write!(f, "{:02x}", c));
                }
                Ok(())
            }
        }
    }
}

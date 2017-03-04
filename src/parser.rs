use std::{self, fmt, iter, io, mem};
use std::collections::VecDeque;
use std::convert::TryFrom;
use std::io::Read;
use std::sync::Arc;
use regex::bytes::Regex;
use debug::debug_utf8;

pub mod delimiter {
    use std;
    use self::Direction::*;
    use self::Delim::*;

    #[derive(Clone, Copy, Debug, Eq, PartialEq)]
    pub enum Direction {
        Open,
        Close,
    }

    impl std::ops::Not for Direction {
        type Output = Self;
        fn not(self) -> Self::Output {
            match self {
                Direction::Open => Direction::Close,
                Direction::Close => Direction::Open,
            }
        }
    }

    #[derive(Clone, Copy, Debug, Eq, PartialEq)]
    pub enum Delim {
        Parenthesis,
        Bracket,
        Brace,
    }

    impl Delim {
        pub fn open(self) -> Delimiter {
            Delimiter(Open, self)
        }
        pub fn close(self) -> Delimiter {
            Delimiter(Close, self)
        }
    }

    #[derive(Clone, Copy, Debug, Eq, PartialEq)]
    pub struct Delimiter(pub Direction, pub Delim);

    impl std::convert::TryFrom<u8> for Delimiter {
        type Err = ();
        fn try_from(d: u8) -> Result<Self, Self::Err> {
            match d {
                b'(' => Ok(Delimiter(Open, Parenthesis)),
                b')' => Ok(Delimiter(Close, Parenthesis)),
                b'[' => Ok(Delimiter(Open, Bracket)),
                b']' => Ok(Delimiter(Close, Bracket)),
                b'{' => Ok(Delimiter(Open, Brace)),
                b'}' => Ok(Delimiter(Close, Brace)),
                _ => Err(()),
            }
        }
    }

    impl Delimiter {
        pub fn as_u8(self) -> u8 {
            self.as_bytes()[0]
        }

        pub fn as_bytes(self) -> &'static [u8] {
            match self {
                Delimiter(Open, Parenthesis) => b"(",
                Delimiter(Close, Parenthesis) => b")",
                Delimiter(Open, Bracket) => b"[",
                Delimiter(Close, Bracket) => b"]",
                Delimiter(Open, Brace) => b"{",
                Delimiter(Close, Brace) => b"}",
            }
        }
    }
}

use self::delimiter::Direction::*;
use self::delimiter::{Delim, Delimiter};

pub fn is_ascii_space(c: u8) -> bool {
    match c {
        b' ' => true,
        _ if c >= 0x9 && c < 0xe => true,
        _ => false,
    }
}

const ESCAPER: u8 = b'\\';
const DIVIDER: u8 = b'|';

fn is_word_char(c: u8) -> bool {
    !(is_ascii_space(c) || c == DIVIDER || c == ESCAPER)
}

/// If `name` is empty, then the location is considered unknown.
#[derive(Clone, Debug)]
pub struct Loc {
    /// Name of the file.
    pub name: Arc<String>,

    /// Zero-based line number.
    pub row: usize,

    /// Zero-based column number.
    pub col: usize,
}

impl Loc {
    pub fn update<I: IntoIterator<Item=u8>>(&mut self, bytes: I) {
        for c in bytes {
            self.col += 1;
            if c == b'\n' {
                self.col = 0;
                self.row += 1;
            }
        }
    }
}

impl<'a> From<&'a str> for Loc {
    fn from(name: &'a str) -> Self {
        Loc {
            name: Arc::new(String::from(name)),
            row: 0,
            col: 0,
        }
    }
}

impl Default for Loc {
    fn default() -> Self {
        Loc::from(<&str>::default())
    }
}

impl fmt::Display for Loc {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        if self.name.is_empty() {
            write!(f, "<unknown>")
        } else {
            write!(f, "{}:{}:{}", self.name, self.row + 1, self.col + 1)
        }
    }
}

#[derive(Clone, Copy)]
enum Token<'a> {
    Chunk(&'a [u8]),
    Tag(&'a [u8], Delimiter),
}

impl<'a> fmt::Debug for Token<'a> {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            &Token::Chunk(ref s) => {
                f.debug_tuple("Chunk")
                    .field(&debug_utf8(s))
                    .finish()
            }
            &Token::Tag(ref w, ref d) => {
                f.debug_tuple("Tag")
                    .field(&debug_utf8(w))
                    .field(&debug_utf8(&[d.as_u8()]))
                    .finish()
            }
        }
    }
}

#[derive(Clone, Debug)]
struct Lexer<'a> {
    input: &'a [u8],
    loc: Loc,
    queue: VecDeque<(Loc, Token<'a>)>,
}

impl<'a> Lexer<'a> {
    fn new(input: &'a [u8], loc: Loc) -> Self {
        Lexer {
            input: input,
            loc: loc,
            queue: VecDeque::new(),
        }
    }

    fn push(&mut self, token: Token<'a>) {
        self.queue.push_back((self.loc.clone(), token));
    }

    fn refill(&mut self) {
        use self::Token::*;

        // end of input
        if self.input.len() == 0 {
            return;
        }

        lazy_static! {
            static ref RE: Regex = Regex::new(concat!(
                r"(?s)",
                r"^(.*?)(",
                r"(:?\\[^ \t\\|()\[\]{}]*)?[\])}]",
                r"|",
                r"[\\|]?[^ \t\\|()\[\]{}]*[(\[{]",
                r")",
            )).unwrap();
        }
        match RE.captures(self.input) {
            None => {                   // last chunk
                self.push(Chunk(self.input));
                self.input = b"";
            }
            Some(caps) => {
                self.input = self.input.split_at(caps.get(0).unwrap().end()).1;
                let chunk = caps.get(1).unwrap().as_bytes();
                let tag = caps.get(2).unwrap().as_bytes();

                let (delim, word) = tag.split_last().unwrap();
                let delim = Delimiter::try_from(*delim).unwrap();
                let word = if let Some((&b'|', word)) = word.split_first() {
                    word
                } else {
                    word
                };

                self.push(Chunk(chunk));
                self.loc.update(chunk.iter().cloned());
                self.push(Tag(word, delim));
                self.loc.update(tag.iter().cloned());
            }
        }
    }
}

impl<'a> Iterator for Lexer<'a> {
    type Item = (Loc, Token<'a>);

    fn next(&mut self) -> Option<Self::Item> {
        if self.queue.is_empty() {
            self.refill()
        }
        self.queue.pop_front()
    }
}

/// Stores binary data.
#[derive(Clone, Default, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Blob(Arc<Box<[u8]>>);

impl Blob {
    pub fn as_bytes(&self) -> &[u8] {
        self
    }

    pub fn as_utf8(&self) -> Result<&str, std::str::Utf8Error> {
        std::str::from_utf8(&self)
    }
}

impl From<Box<[u8]>> for Blob {
    fn from(s: Box<[u8]>) -> Self {
        Blob(Arc::new(s))
    }
}

impl From<Vec<u8>> for Blob {
    fn from(s: Vec<u8>) -> Self {
        Self::from(s.into_boxed_slice())
    }
}

impl<'a> From<&'a [u8]> for Blob {
    fn from(s: &'a [u8]) -> Self {
        Self::from(s.to_vec())
    }
}

impl<'a> From<&'a str> for Blob {
    fn from(s: &'a str) -> Self {
        Self::from(s.as_bytes())
    }
}

impl std::borrow::Borrow<[u8]> for Blob {
    fn borrow(&self) -> &[u8] {
        self
    }
}

impl std::convert::AsRef<[u8]> for Blob {
    fn as_ref(&self) -> &[u8] {
        self
    }
}

impl std::ops::Deref for Blob {
    type Target = [u8];
    fn deref(&self) -> &[u8] {
        &self.0
    }
}

impl fmt::Debug for Blob {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        f.debug_tuple("Blob")
            .field(&debug_utf8(self))
            .finish()
    }
}

impl<'a, 'b> std::ops::Add<&'b Blob> for &'a Blob{
    type Output = Blob;
    fn add(self, rhs: &'b Blob) -> Self::Output {
        let mut v = self.0.to_vec();
        v.extend(rhs.iter());
        Blob(Arc::new(v.into_boxed_slice()))
    }
}

#[derive(Clone, Debug)]
pub struct Elem {
    pub name: Blob,
    pub delim: Delim,
    pub children: Vec<Node>,
    pub loc: Loc,
}

fn escape_delim<'a>(delim: Delimiter) -> Node {
    Node::Elem(Elem {
        name: Blob::from(&[ESCAPER] as &[u8]),
        delim: Delim::Parenthesis,
        children: vec![Node::from(delim.as_bytes())],
        loc: Default::default(),
    })
}

impl Elem {
    /// Melt the node into a mix of text nodes and child nodes.
    /// The closing delimiter is not included.
    fn into_text_nodes(self) -> impl Iterator<Item=Node> {
        let delim = self.delim.open();
        iter::once(Node::Text(self.name))
            .chain(iter::once(escape_delim(delim)))
            .chain(self.children.into_iter())
    }
}

pub trait WriteTo {
    type State;
    fn write_to<W>(&self, f: &mut W, s: &mut Self::State)
                   -> io::Result<()> where W: io::Write;
}

fn write_to_vec<T: ?Sized>(x: &T, s: &mut T::State)
                           -> Vec<u8> where T: WriteTo {
    let mut v = Vec::new();
    x.write_to(&mut v, s).unwrap();
    v
}

impl<'a> WriteTo for [u8] {
    type State = ();
    fn write_to<W>(&self, f: &mut W, _: &mut Self::State)
                   -> io::Result<()> where W: io::Write {
        f.write_all(self)
    }
}

pub enum NodeWriteState { Clean, Sticky }

impl<'a> WriteTo for [Node] {
    type State = NodeWriteState;
    fn write_to<W>(&self, f: &mut W, s: &mut Self::State)
                   -> io::Result<()> where W: io::Write {
        for x in self {
            x.write_to(f, s)?
        }
        Ok(())
    }
}

impl WriteTo for Node {
    type State = NodeWriteState;
    fn write_to<W>(&self, f: &mut W, s: &mut Self::State)
                   -> io::Result<()> where W: io::Write {
        match self {
            &Node::Text(ref t) => {
                t.write_to(f, &mut ())?;
                if is_word_char(*t.last().unwrap_or(&b' ')) {
                    *s = NodeWriteState::Sticky;
                } else {
                    *s = NodeWriteState::Clean;
                }
            }
            &Node::Elem(ref elem) => {
                if let &mut NodeWriteState::Sticky = s {
                    [DIVIDER].write_to(f, &mut ())?;
                }
                elem.name.write_to(f, &mut ())?;
                elem.delim.open().as_bytes().write_to(f, &mut ())?;
                elem.children.write_to(f, s)?;
                if is_literal(&elem.name) {
                    elem.name.write_to(f, &mut ())?;
                }
                elem.delim.close().as_bytes().write_to(f, &mut ())?;
                *s = NodeWriteState::Clean;
            },
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub enum Node {
    Text(Blob),
    Elem(Elem),
}

impl<'a> From<&'a [u8]> for Node {
    fn from(s: &'a [u8]) -> Self {
        Node::Text(Blob::from(s))
    }
}

impl<'a> From<&'a str> for Node {
    fn from(s: &'a str) -> Self {
        Node::Text(Blob::from(s))
    }
}

pub fn is_literal(name: &[u8]) -> bool {
    match name.first() {
        Some(&ESCAPER) => true,
        _ => false,
    }
}

impl Node {
    pub fn parse(s: &[u8], path: &str) ->(Vec<Self>, Vec<String>) {
        Node::parse_tokens(Lexer::new(&s, Loc::from(path)))
    }

    fn parse_tokens<'a, I>(tokens: I) -> (Vec<Self>, Vec<String>)
        where I: Iterator<Item=(Loc, Token<'a>)>
    {
        let mut errs = Vec::new();
        let mut stack = Vec::new();
        let mut top = Elem {
            name: Blob::default(),
            delim: Delim::Parenthesis,
            children: Vec::new(),
            loc: Default::default(),
        };
        for token in tokens {
            let esc = is_literal(&top.name);
            match token {
                (_, Token::Chunk(s)) => {
                    top.children.push(Node::from(s));
                }
                (loc, Token::Tag(word, delim)) => match delim {
                    _ if esc && top.name.as_bytes() != word => {
                        top.children.push(Node::from(word));
                        top.children.push(Node::from(delim.as_bytes()));
                    }
                    Delimiter(Open, dtype) => {
                        stack.push(top);
                        top = Elem {
                            name: Blob::from(word),
                            delim: dtype,
                            children: Vec::new(),
                            loc: loc,
                        };
                    }
                    Delimiter(Close, dtype) => {
                        if !esc {
                            top.children.push(Node::from(word));
                        }
                        if top.delim != dtype {
                            let d = Delimiter(Open, top.delim);
                            errs.push(format!(
                                "{}: ‘{}’ doesn’t close ‘{}{}’ at {}",
                                loc,
                                String::from_utf8_lossy(delim.as_bytes()),
                                debug_utf8(&top.name),
                                String::from_utf8_lossy(d.as_bytes()),
                                top.loc));
                            top.children.push(escape_delim(d));
                        } else {
                            match stack.pop() {
                                None => {
                                    // we're at root level (which is never
                                    // an escaping context), so there's
                                    // nothing to close
                                    let d = delim.as_bytes();
                                    errs.push(format!(
                                        "{}: ‘{}’ doesn’t close anything",
                                        loc, String::from_utf8_lossy(d)));
                                    top.children.push(Node::from(d));
                                }
                                Some(mut new_top) => {
                                    new_top.children.push(Node::Elem(Elem {
                                        name: top.name,
                                        delim: top.delim,
                                        children: top.children,
                                        loc: top.loc,
                                    }));
                                    top = new_top;
                                }
                            }
                        }
                    }
                }
            }
        }
        let mut nodes = mem::replace(match stack.first_mut() {
            Some(root) => {
                let d = Delimiter(Open, top.delim).as_bytes();
                errs.push(format!(
                    "{}: ‘{}{}’ was never closed",
                    top.loc,
                    String::from_utf8_lossy(&top.name),
                    String::from_utf8_lossy(&d)));
                &mut root.children
            }
            None => &mut top.children,
        }, Vec::new());
        // flatten the unclosed elements into text
        for elem in stack.into_iter().chain(iter::once(top)).skip(1) {
            nodes.extend(elem.into_text_nodes());
        }
        (nodes, errs)
    }
}

pub fn load_file(path: &str) -> Vec<u8> {
    let mut f = std::fs::File::open(path).unwrap();
    let mut s = Vec::new();
    let _ = f.read_to_end(&mut s).unwrap();
    s
}

pub fn render_doc(nodes: &[Node]) -> Vec<u8> {
    write_to_vec(nodes, &mut NodeWriteState::Clean)
}

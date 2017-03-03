use std::{self, fmt, io, mem};
use debug::debug_utf8;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Delim<T> { Open(T), Close(T) }

impl<T> std::ops::Not for Delim<T> {
    type Output = Self;
    fn not(self) -> Self::Output {
        use self::Delim::*;
        match self {
            Open(x) => Close(x),
            Close(x) => Open(x),
        }
    }
}

impl<T> Delim<T> {
    pub fn value(&self) -> &T {
        match self {
            &Delim::Open(ref x) => x,
            &Delim::Close(ref x) => x,
        }
    }

    pub fn value_mut(&mut self) -> &mut T {
        match self {
            &mut Delim::Open(ref mut x) => x,
            &mut Delim::Close(ref mut x) => x,
        }
    }

    pub fn into_value(self) -> T {
        match self {
            Delim::Open(x) => x,
            Delim::Close(x) => x,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DelimType { Bracket, Parenthesis, Brace }

impl Delim<DelimType> {
    pub fn from_u8(d: u8) -> Option<Self> {
        use self::Delim::*;
        use self::DelimType::*;
        match d {
            b'(' => Some(Open(Parenthesis)),
            b')' => Some(Close(Parenthesis)),
            b'[' => Some(Open(Bracket)),
            b']' => Some(Close(Bracket)),
            b'{' => Some(Open(Brace)),
            b'}' => Some(Close(Brace)),
            _ => None,
        }
    }

    pub fn to_u8(&self) -> u8 {
        self.as_bytes()[0]
    }

    pub fn as_bytes(&self) -> &'static [u8] {
        use self::Delim::*;
        use self::DelimType::*;
        match self {
            &Open(Parenthesis) => b"(",
            &Close(Parenthesis) => b")",
            &Open(Bracket) => b"[",
            &Close(Bracket) => b"]",
            &Open(Brace) => b"{",
            &Close(Brace) => b"}",
        }
    }
}

pub fn is_ascii_space(c: u8) -> bool {
    match c {
        b' ' => true,
        _ if c >= 0x9 && c < 0xe => true,
        _ => false,
    }
}

/// If `name` is empty, then the location is considered unknown.
#[derive(Clone, Copy, Debug)]
pub struct Loc<'a> {
    pub name: &'a str,
    pub row: usize,
    pub col: usize,
}

impl<'a> Loc<'a> {
    pub fn new(name: &'a str) -> Self {
        Loc { name: name, row: 0, col: 0 }
    }
}

impl<'a> Default for Loc<'a> {
    fn default() -> Self {
        Loc::new("")
    }
}

impl<'a> fmt::Display for Loc<'a> {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        if self.name.is_empty() {
            write!(f, "<unknown>")
        } else {
            write!(f, "{}:{}:{}", self.name, self.row + 1, self.col + 1)
        }
    }
}

#[derive(Clone, Copy)]
enum Token<'a>{
    Chunk(Loc<'a>, &'a [u8]),
    Tag(Loc<'a>, &'a [u8], Delim<DelimType>),
}

impl<'a> fmt::Debug for Token<'a> {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            &Token::Chunk(ref loc, ref s) => {
                f.debug_tuple("Chunk")
                    .field(loc)
                    .field(&debug_utf8(s))
                    .finish()
            }
            &Token::Tag(ref loc, ref w, ref d) => {
                f.debug_tuple("Tag")
                    .field(loc)
                    .field(&debug_utf8(w))
                    .field(&debug_utf8(&[d.to_u8()]))
                    .finish()
            }
        }
    }
}

#[derive(Clone, Copy, Debug)]
struct Lexer<'a> {
    input: &'a [u8],
    loc: Loc<'a>,
    state: Option<(&'a [u8], Delim<DelimType>)>,
}

impl<'a> Lexer<'a> {
    fn new(input: &'a [u8], loc: Loc<'a>) -> Self {
        Lexer { input: input, loc: loc, state: None }
    }
}

/// Find the element for which the predicate is true, and then make a split
/// immediately afterwards.  If not found, returns `None`.
fn slice_split2<T, R, F>(s: &[T], mut pred: F) -> Option<(&[T], R, &[T])>
    where F: FnMut(&T) -> Option<R> {
    for (i, c) in s.into_iter().enumerate() {
        if let Some(r) = pred(c) {
            return Some((s.split_at(i).0, r, s.split_at(i + 1).1));
        }
    }
    None
}

/// The first element is the longest suffix of elements that satisfies the
/// predicate.  The second element is the remaining part.
fn slice_rspan<T, F>(s: &[T], mut pred: F) -> (&[T], &[T])
    where F: FnMut(&T) -> bool {
    let mut j = s.len();
    for (i, c) in s.into_iter().enumerate().rev() {
        if !pred(c) {
            break;
        }
        j = i;
    }
    let (suffix, rest) = s.split_at(j);
    (rest, suffix)
}

const ESCAPER: u8 = b'\\';
const DIVIDER: u8 = b'|';

fn is_word_char(c: u8) -> bool {
    !(is_ascii_space(c) || c == DIVIDER || c == ESCAPER)
}

impl<'a> Iterator for Lexer<'a> {
    type Item = Token<'a>;
    fn next(&mut self) -> Option<Self::Item> {
        match mem::replace(&mut self.state, None) {
            None => {
                // end of input
                if self.input.len() == 0 {
                    return None;
                }
                // find the next delimiter
                let loc = self.loc;
                match slice_split2(self.input, |c| {
                    let delim = Delim::from_u8(*c);
                    if delim.is_none() {
                        self.loc.col += 1;
                        if *c == b'\n' {
                            self.loc.col = 0;
                            self.loc.row += 1;
                        }
                    }
                    delim
                }) {
                    None => { // no delimiter
                        let chunk = self.input;
                        self.input = &[];
                        Some(Token::Chunk(loc, chunk))
                    }
                    Some((pre, delim, input)) => { // found delimiter
                        self.input = input;
                        let mut stop = false;
                        let (word, chunk) = slice_rspan(pre, |&c| {
                            match c {
                                ESCAPER => {
                                    stop = true;
                                    true
                                },
                                _ => {
                                    !stop && is_word_char(c)
                                }
                            }
                        });
                        let chunk = match chunk.split_last() {
                            Some((&c, rest)) if c == DIVIDER => rest,
                            _ => chunk,
                        };
                        // assuming words can never contain newlines
                        self.loc.col -= word.len();
                        self.state = Some((word, delim));
                        Some(Token::Chunk(loc, chunk))
                    }
                }
            }
            // we still have a tag from the previous iteration
            Some((word, delim)) => {
                let loc = self.loc;
                // assuming delimiters are never newlines
                self.loc.col += word.len() + 1;
                return Some(Token::Tag(loc, word, delim));
            }
        }
    }
}

#[derive(Clone, Debug)]
pub struct Elem<T, L> {
    pub name: T,
    pub delim: DelimType,
    pub children: Vec<Node<T, L>>,
    pub loc: L,
}

type IntoTextNodesIter<T> =
    ::std::iter::Chain<::std::iter::Chain<::std::iter::Once<T>,
                                          ::std::iter::Once<T>>,
                       ::std::vec::IntoIter<T>>;

fn escape_delim<'a, L: Default>(delim: Delim<DelimType>)
                                -> Node<&'a [u8], L> {
    const ESCAPER_BYTES: &[u8] = &[ESCAPER];
    Node::Elem(Elem {
        name: ESCAPER_BYTES,
        delim: DelimType::Parenthesis,
        children: vec![Node::Text(delim.as_bytes())],
        loc: L::default(),
    })
}

impl<'a, L> Elem<&'a [u8], L> {
    /// Melt the node into a mix of text nodes and child nodes.
    /// The closing delimiter is not included.
    fn into_text_nodes(self) -> IntoTextNodesIter<Node<&'a [u8], L>>
        where L: Default {
        use std::iter::once;
        let delim = Delim::Open(self.delim);
        once(Node::Text(self.name))
            .chain(once(escape_delim(delim)))
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

impl<'a, L> WriteTo for [Node<&'a [u8], L>] {
    type State = NodeWriteState;
    fn write_to<W>(&self, f: &mut W, s: &mut Self::State)
                   -> io::Result<()> where W: io::Write {
        for x in self {
            x.write_to(f, s)?
        }
        Ok(())
    }
}

impl<'a, L> WriteTo for Node<&'a [u8], L> {
    type State = NodeWriteState;
    fn write_to<W>(&self, f: &mut W, s: &mut Self::State)
                   -> io::Result<()> where W: io::Write {
        match self {
            &Node::Text(t) => {
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
                Delim::Open(elem.delim).as_bytes().write_to(f, &mut ())?;
                elem.children.write_to(f, s)?;
                if is_literal(elem.name) {
                    elem.name.write_to(f, &mut ())?;
                }
                Delim::Close(elem.delim).as_bytes().write_to(f, &mut ())?;
                *s = NodeWriteState::Clean;
            },
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub enum Node<T, L> {
    Text(T),
    Elem(Elem<T, L>),
}

pub fn is_literal(name: &[u8]) -> bool {
    match name.first() {
        Some(&ESCAPER) => true,
        _ => false,
    }
}

impl<'a> Node<&'a [u8], Loc<'a>> {
    pub fn parse(s: &'a [u8], path: &'a str) ->(Vec<Self>, Vec<String>) {
        Node::parse_tokens(Lexer::new(&s, Loc::new(path)))
    }

    fn parse_tokens<I: Iterator<Item=Token<'a>>>(tokens: I)
                                                 -> (Vec<Self>, Vec<String>) {
        let mut errs = Vec::new();
        let mut stack = Vec::new();
        let mut top = Elem {
            name: &[] as &[u8],
            delim: DelimType::Parenthesis,
            children: Vec::new(),
            loc: Default::default(),
        };
        for token in tokens {
            let esc = is_literal(top.name);
            match token {
                Token::Chunk(_, s) => {
                    top.children.push(Node::Text(s));
                }
                Token::Tag(loc, word, delim) => match delim {
                    _ if esc && top.name != word => {
                        top.children.push(Node::Text(word));
                        top.children.push(Node::Text(delim.as_bytes()));
                    }
                    Delim::Open(dtype) => {
                        stack.push(top);
                        top = Elem {
                            name: word,
                            delim: dtype,
                            children: Vec::new(),
                            loc: loc,
                        };
                    }
                    Delim::Close(dtype) => {
                        if !esc {
                            top.children.push(Node::Text(word));
                        }
                        if top.delim != dtype {
                            let d = Delim::Open(top.delim);
                            errs.push(format!(
                                "{}: ‘{}’ doesn’t close ‘{}{}’ at {}",
                                loc,
                                String::from_utf8_lossy(delim.as_bytes()),
                                debug_utf8(top.name),
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
                                    top.children.push(Node::Text(d));
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
                let d = Delim::Open(top.delim).as_bytes();
                errs.push(format!(
                    "{}: ‘{}{}’ was never closed",
                    top.loc,
                    String::from_utf8_lossy(top.name),
                    String::from_utf8_lossy(d)));
                &mut root.children
            }
            None => &mut top.children,
        }, Vec::new());
        // flatten the unclosed elements into text
        for elem in stack.into_iter().chain(::std::iter::once(top)).skip(1) {
            nodes.extend(elem.into_text_nodes());
        }
        (nodes, errs)
    }
}

pub fn load_file(path: &str) -> Vec<u8> {
    use std::io::Read;
    use std::fs::File;
    let mut f = File::open(path).unwrap();
    let mut s = Vec::new();
    let _ = f.read_to_end(&mut s).unwrap();
    s
}

pub fn render_doc(nodes: &[Node<&[u8], Loc>]) -> Vec<u8> {
    write_to_vec(nodes, &mut NodeWriteState::Clean)
}

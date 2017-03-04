extern crate snep;
use std::io;
use snep::parser::{self, Node, Elem};

struct Html<'a>(&'a [Node]);

impl<'a> std::fmt::Display for Html<'a> {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        for child in self.0 {
            HtmlNode(child).fmt(f)?;
        }
        Ok(())
    }
}

struct HtmlNode<'a>(&'a Node);

impl<'a> std::fmt::Display for HtmlNode<'a> {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        // TODO: implement HTML escaping and sanity checks!
        use parser::is_literal;
        match self.0 {
            &Node::Text(ref t) => {
                t.fmt(f)?;
            }
            &Node::Elem(ref elem) => {
                let name = &elem.name;
                if is_literal(name) {
                    Html(&elem.children).fmt(f)?;
                } else if name.is_empty() || name.ends_with("=") {
                    name.fmt(f)?;
                    elem.delim.open().fmt(f);
                    Html(&elem.children).fmt(f)?;
                    elem.delim.close().fmt(f);
                } else if (name as &str) == "+" {
                    for child in &elem.children {
                        match child {
                            &Node::Elem(ref elem) => {
                                Html(&elem.children).fmt(f)?;
                            }
                            _ => {}
                        }
                    }
                } else {
                    f.write_str(&format!("<{}>", name))?;
                    Html(&elem.children).fmt(f)?;
                    f.write_str(&format!("</{}>", name))?;
                }
            },
        }
        Ok(())
    }
}

fn main() {
    use std::io::{Write, stderr};
    use std::process::exit;
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 2 {
        writeln!(stderr(), "need 1 command-line argument").unwrap();
        exit(1);
    }
    let path = &args[1];
    let s = parser::load_file(path);
    let (nodes, errs) = parser::Node::parse(&s, path);
    for err in &errs {
        writeln!(stderr(), "{}", err).unwrap();
    }
    print!("{}", parser::Nodes(nodes.iter()));
    if !errs.is_empty() {
        exit(1);
    }
    let mut f = std::fs::File::create("output.html").unwrap();
    write!(f, "{}", Html(&nodes)).unwrap();
}

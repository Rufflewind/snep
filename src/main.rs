extern crate snep;
use std::io;
use snep::parser::{self, Node, Elem};

fn write_children<L, W: io::Write>(f: &mut W, elem: &Elem<&[u8], L>)
                                   -> io::Result<()> {
    for child in &elem.children {
        write_html(child, f)?;
    }
    Ok(())
}

fn write_html<L, W: io::Write>(node: &Node<&[u8], L>, f: &mut W)
                               -> io::Result<()> {
    // TODO: implement HTML escaping and sanity checks!
    use parser::{Delim, WriteTo, is_literal};
    match node {
        &Node::Text(t) => {
            f.write_all(t)?;
        }
        &Node::Elem(ref elem) => {
            let name = elem.name;
            if is_literal(name) {
                write_children(f, elem)?;
            } else if name.is_empty() || name.last() == Some(&b'=') {
                f.write_all(name)?;
                Delim::Open(elem.delim).as_bytes().write_to(f, &mut ())?;
                write_children(f, elem)?;
                Delim::Close(elem.delim).as_bytes().write_to(f, &mut ())?;
            } else if name == b"+" {
                for child in &elem.children {
                    match child {
                        &Node::Elem(ref elem) => {
                            write_children(f, elem)?;
                        }
                        _ => {}
                    }
                }
            } else {
                f.write_all("<".as_bytes())?;
                f.write_all(name)?;
                f.write_all(">".as_bytes())?;
                write_children(f, elem)?;
                f.write_all("</".as_bytes())?;
                f.write_all(name)?;
                f.write_all(">".as_bytes())?;
            }
        },
    }
    Ok(())
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
    print!("{}", String::from_utf8_lossy(&parser::render_doc(&nodes)));
    if !errs.is_empty() {
        exit(1);
    }
    let mut f = std::fs::File::create("output.html").unwrap();
    for node in &nodes {
        write_html(node, &mut f);
    }
}

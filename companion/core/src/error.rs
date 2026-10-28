use thiserror::Error;

#[derive(Debug, Error)]
pub enum CoreError {
    #[error("lecture ou écriture impossible : {0}")]
    Io(#[from] std::io::Error),
    #[error("le site ne répond pas : {0}")]
    Http(#[from] reqwest::Error),
    #[error("{message}")]
    Api { status: u16, message: String },
    #[error("ce code a déjà été importé")]
    Duplicate,
    #[error("{0}")]
    Parse(String),
    #[error("{0}")]
    Config(String),
}

pub type Result<T> = std::result::Result<T, CoreError>;

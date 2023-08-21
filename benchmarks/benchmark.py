SUBJECTS=('PySnooper','ansible','black','cookiecutter','fastapi','httpie','keras','luigi','matplotlib','pandas',
          'sanic','scrapy','spacy','thefuck','tornado','tqdm','youtube-dl')

BUGS_NUMBER={
    'PySnooper':3,
    'ansible':18,
    'black':23,
    'cookiecutter':4,
    'fastapi':16,
    'httpie':5,
    'keras':45,
    'luigi':33,
    'matplotlib':30,
    'pandas':169,

    'sanic':5,
    'scrapy':40,
    'spacy':10,
    'thefuck':32,
    'tornado':16,
    'tqdm':9,
    'youtube-dl':43
}

EXCEPT_BUGS=(('cookiecutter',1),('cookiecutter',2),('cookiecutter',3),('cookiecutter',4),  # cookiecutter: Add PYTHONPATH to .bashrc
             ('PySnooper',2),  # PySnooper: Import error
             )
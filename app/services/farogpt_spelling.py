"""Bounded spelling proposals; callers must ask for confirmation, never execute them."""
import re
import unicodedata
from functools import lru_cache
from itertools import islice, product


# Canonical report terms, not a growing list of misspellings. Report aliases,
# months and the parser's accepted vocabulary are supplied by the caller.
REPORT_WORDS = frozenset(('matematicas espanol ingles ciencias educacion especial kindergarten kinder '
    'reclutados talleres prevencion porcentaje femenino femeninos masculino masculinos '
    'internos externos agencias semanas grado certificados certificadas clasificacion '
    'seguimiento global globales residenciales vigente activa actual anterior pasado '
    'completo campos indicadores que lista listame tienen les propuestas nivel general todo '
    'codigos filtro cumplen cumplidas incumplidas tutorias tutoria escuela asisten casos '
    'participacion seleccionar clasificadas').split())
PRESERVE_WORDS = frozenset(('no sin con solo solamente excepto excluyendo nunca menores mayores '
    'entre desde hasta antes despues distintos diferentes todos todas nota promedio').split())
ENTITY_BOUNDARIES = frozenset('en para durante mes meses ano enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split())
AFTER_EN = frozenset('enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre matematicas espanol ingles ciencias'.split())


def _fold(word):
    return ''.join(c for c in unicodedata.normalize('NFKD', word.lower()) if not unicodedata.combining(c))


def _tokens(text):
    return list(re.finditer(r'[^\W_]+', text))


def _distance(left, right):
    """Optimal string alignment distance, including adjacent transpositions."""
    rows = [list(range(len(right) + 1))]
    for i, char in enumerate(left, 1):
        row = [i]
        for j, other in enumerate(right, 1):
            value = min(row[j - 1] + 1, rows[-1][j] + 1,
                        rows[-1][j - 1] + (char != other))
            if i > 1 and j > 1 and char == right[j - 2] and left[i - 2] == other:
                value = min(value, rows[-2][j - 2] + 1)
            row.append(value)
        rows.append(row)
    return rows[-1][-1]


@lru_cache(maxsize=512)
def _candidates(word, vocabulary):
    limit = 2 if len(word) >= 7 else 1
    matches = []
    best = limit + 1
    for candidate in vocabulary:
        if not 4 <= len(candidate) <= 32 or abs(len(word) - len(candidate)) > limit:
            continue
        distance = _distance(word, candidate)
        if distance < best:
            best, matches = distance, [candidate]
        elif distance == best:
            matches.append(candidate)
    return tuple(matches) if best <= limit else ()


def propose(question, phrases, *, protected_phrases=()):
    """Return at most three complete questions, preserving every other character."""
    if not question or len(question) > 800:
        return []
    vocabulary = tuple(sorted(REPORT_WORDS | {
        _fold(match.group()) for phrase in phrases for match in _tokens(phrase)}))
    known = set(vocabulary) | PRESERVE_WORDS
    protected = {_fold(match.group()) for phrase in protected_phrases for match in _tokens(phrase)}
    matches = _tokens(question)
    replacements = []
    entity = False
    for index, match in enumerate(matches):
        word = _fold(match.group())
        if entity and (word in ENTITY_BOUNDARIES or re.fullmatch(r'20\d{2}|2100', word)):
            entity = False
        if word in {'residencial', 'propuesta'}:
            entity = True
            continue
        if entity:
            # Explicit identifiers (including unknown names) are not spellchecked.
            if any(char.isdigit() for char in word) or word in {'activa', 'vigente', 'actual'}:
                entity = False
            continue
        if word in known or word in protected or not word.isalpha() or not 4 <= len(word) <= 32:
            continue
        choices = _candidates(word, vocabulary)
        previous = index - 1
        while previous >= 0 and _fold(matches[previous].group()) in {'el', 'la', 'los', 'las'}:
            previous -= 1
        if previous >= 0 and _fold(matches[previous].group()) == 'en' and not (choices and set(choices) <= AFTER_EN):
            # An unknown location after "en" stays literal. Months and school
            # subjects are the supported non-location interpretations here.
            entity = True
            continue
        if choices:
            replacements.append((match.start(), match.end(), choices))
    if not replacements:
        return []
    suggestions = []
    for choices in islice(product(*(item[2] for item in replacements)), 3):
        pieces, offset = [], 0
        for (start, end, _), correction in zip(replacements, choices):
            pieces.extend((question[offset:start], correction))
            offset = end
        pieces.append(question[offset:])
        suggestion = ''.join(pieces)
        if len(suggestion) <= 800:
            suggestions.append(suggestion)
    return suggestions

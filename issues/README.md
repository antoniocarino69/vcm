# Issue tracker locale (fino al remote)

Ogni problema o richiesta diventa un file `NNNN-titolo-breve.md` (numero
progressivo a 4 cifre). Template:

```markdown
# NNNN — Titolo breve

## Contesto
Descrizione del problema/della richiesta, ambiente, versione/commit.

## Riproduzione (per i bug)
Passi esatti per riprodurre, output atteso vs reale.

## Comportamento atteso
Cosa dovrebbe succedere.

## Stato
- aperta | in corso | chiusa
- branch: fix/NNNN-... (se in corso)
- chiusa da: <commit> (quando risolta)
```

Convenzione commit: `fix(#NNNN): ...` e nel corpo `Closes #NNNN`.

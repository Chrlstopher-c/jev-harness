() => {
  const d = document.getElementById('board').dataset;
  return {
    fen: d.fen, turn: d.turn, mine: d.human, status: d.status, last: d.last || '',
    eval: d.eval || '', thinking: d.thinking,
  };
}

// Aplica o tema (escuro por padrão) antes de a página ser pintada, para não piscar.
// Carregado como script comum no <head> de todas as páginas; a escolha fica em localStorage ("nexar_tema").
(function () {
  var escuro = true;
  try {
    escuro = localStorage.getItem("nexar_tema") !== "claro";
  } catch (e) {
    // armazenamento bloqueado: tema escuro
  }
  if (escuro) document.documentElement.classList.add("dark");
})();

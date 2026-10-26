// Execute no console do navegador, na página https://consumidor.gov.br.
// Selecione data/BaseUrl.json quando o seletor abrir.
(async () => {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".json,application/json";
  input.addEventListener("change", async () => {
    try {
      const file = input.files[0];
      if (!file) return;
      const data = JSON.parse(await file.text());
      if (!Array.isArray(data)) throw new Error("O JSON deve conter uma lista.");

      const arquivos = data.filter(item =>
        typeof item?.texto === "string" && item.texto.startsWith(
          "Arquivo em formato CSV com dados de todas as reclamações finalizadas"
        )
      );
      console.log(`${arquivos.length} arquivos encontrados.`);

      for (const item of arquivos) {
        if (!item.codigo || !item.nomeArquivo) {
          console.warn("Publicação sem código ou nome de arquivo:", item);
          continue;
        }
        const url = `https://consumidor.gov.br/pages/publicacao/externo/${encodeURIComponent(item.codigo)}/download`;
        const a = document.createElement("a");
        a.href = url;
        a.download = item.nomeArquivo;
        document.body.appendChild(a);
        a.click();
        a.remove();
        console.log("Download solicitado:", item.nomeArquivo, url);
        await new Promise(r => setTimeout(r, 1500));
      }
      console.log("Solicitações concluídas. Confira os downloads no navegador.");
    } catch (error) {
      console.error("Falha na extração:", error);
    } finally {
      input.remove();
    }
  }, { once: true });
  input.addEventListener("cancel", () => input.remove(), { once: true });
  input.hidden = true;
  document.body.appendChild(input);
  input.click();
})();

# Az IPTV: catalogo para Azamerica S1009+

Este diretorio e consultado pelo complemento Az IPTV instalado no receptor.
`catalog.json` contem as listas e a assinatura digital. O aparelho verifica a
assinatura antes de trocar o catalogo guardado em sua memoria.
`app-code-0.3.1.zip` e a atualizacao de codigo indicada por esse catalogo.
O ZIP `plugin.video.az_iptv-0.3.1.zip` permite uma instalacao completa no XBMC;
o codigo-fonte correspondente esta em `app/`.

O arquivo `demo.mp4` e apenas um teste de 15 segundos com imagem e audio.
As listas IPTV ja existentes na raiz deste fork nao sao importadas
automaticamente: elas incluem conteudo cuja autorizacao de redistribuicao
nao foi estabelecida e varios formatos ainda nao foram validados no S1009+.

Para publicar uma revisao: editar `catalog_source.json` no computador de
desenvolvimento, incrementar `revision`, executar `create_catalog_release.py`
e enviar o novo `catalog.json` para esta pasta. A chave privada usada nessa
assinatura deve permanecer fora do GitHub e do receptor.

O aplicativo atual abre pelo XBMC do receptor. Um atalho no menu APP do
firmware ainda nao foi identificado. O aparelho precisa de internet para
reproduzir um endereco remoto e atualizar o catalogo, mas nao precisa manter
o notebook conectado depois de receber uma conexao de rede propria.

# Política de Privacidade — Slowed Reverb Channel

**Última atualização:** 23 de junho de 2026

## Visão geral

Esta aplicação ("o App") é uma ferramenta pessoal de uso privado, mantida por
Wesley Oliveira, para automatizar a publicação de conteúdo nos canais do próprio
autor. O App não é um produto comercial, não possui usuários além do próprio
autor e não oferece cadastro ou login para terceiros.

## Quais dados são acessados

O App utiliza as APIs oficiais do YouTube e do Pinterest **exclusivamente na
conta do próprio autor**, mediante autorização OAuth 2.0 concedida por ele
mesmo. Especificamente, o App:

- **Pinterest:** cria pins (publica imagens) e lê a lista de boards da conta do
  autor, usando os escopos `pins:write` e `boards:read`.
- **YouTube:** faz upload de vídeos para o canal do autor.

As imagens publicadas são geradas pelo próprio autor por meio do seu pipeline de
produção; nenhuma imagem ou dado de terceiros é coletado, processado ou enviado.

## Armazenamento de dados

Os tokens de autorização (`youtube_token.json`, `pinterest_token.json`) são
gerados pelo fluxo OAuth e armazenados **localmente**, apenas na máquina do
autor. Eles não são compartilhados, transmitidos a terceiros, nem versionados no
repositório.

O App **não coleta, armazena ou compartilha** dados pessoais de qualquer outra
pessoa.

## Compartilhamento com terceiros

Nenhum dado é compartilhado com terceiros. As únicas comunicações externas são as
chamadas às APIs oficiais do YouTube e do Pinterest, necessárias para a própria
funcionalidade do App, sempre dentro da conta do autor.

## Retenção e exclusão

Como o App não armazena dados de terceiros, não há dados a serem retidos ou
excluídos. Os tokens locais podem ser revogados a qualquer momento nas
configurações de segurança das contas Google e Pinterest do autor.

## Contato

Dúvidas sobre esta política podem ser enviadas para:
**wbfoliveira@gmail.com**

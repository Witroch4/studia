Flashcard: Mecânica dos Solos: Fórmula do Fator Tempo ($T_v$)
Frente: Qual é a fórmula do Fator Tempo ($T_v$)? O que representa cada termo da fórmula? Qual é o cuidado principal com o termo $H_d$?
Verso:
<resumo>

$$T_v = \frac{C_v \cdot t}{H_d^2}$$

</resumo>

**Termos:**

* $T_v$: Fator tempo (adimensional).
* $C_v$: Coeficiente de adensamento do solo (ex: $m^2/ano$, $cm^2/s$).
* $t$: Tempo decorrido após a aplicação da carga.
* $H_d$: Maior caminho de drenagem da água.

<atencao>Cuidado com a Drenagem ($H_d$):</atencao>

* <destaque>Drenagem Dupla</destaque> (ex: argila entre duas camadas de areia): $H_d = \frac{H}{2}$ (metade da espessura da camada).
* <destaque>Drenagem Simples</destaque> (ex: argila sobre rocha impermeável): $H_d = H$ (toda a espessura da camada).
Dica de Concurso: O $T_v$ está diretamente ligado ao Grau de Adensamento ($U\%$). Memorize os notáveis: Para $U = 50\%$, o $T_v \approx 0,197$. Para $U = 90\%$, o $T_v = 0,848$.

Flashcard: Mecânica dos Solos: Casagrande vs. Taylor
Frente: Qual a escala de tempo utilizada em cada método? Qual o grau de adensamento ($U\%$) determinado por cada um deles para o cálculo do $C_v$?
Verso:

<resumo>**Diferenças Fundamentais:**</resumo>

**Método de Casagrande:**

* **Escala:** <destaque>$\log(t)$</destaque> (Logarítmica).
* **Ponto Notável:** $100\%$ de adensamento ($d_{100}$).
* **Técnica:** Interseção de duas tangentes.

**Método de Taylor:**

* **Escala:** <destaque>$\sqrt{t}$</destaque> (Raiz Quadrada).
* **Ponto Notável:** $90\%$ de adensamento ($d_{90}$).
* **Técnica:** Reta auxiliar com abscissas $1,15$ vezes maiores.
Dica de Concurso: O $C_v$ obtido por Taylor costuma ser levemente maior que o de Casagrande. Na dúvida teórica, o Casagrande é considerado mais conservador para o adensamento primário.

Flashcard: Geotecnia: Bulbo de Tensões e Finalidade
Frente: Qual a importância do bulbo de tensões na análise de solos para fundações superficiais?
Verso:

O bulbo de tensões define a <destaque>região limite de influência da carga</destaque>.

É até essa profundidade que devemos estudar a resistência e o módulo de elasticidade do solo, pois é onde o acréscimo de carga é significativo para causar deformações ou ruptura.
Dica de Concurso: Bancas adoram relacionar o bulbo com a Teoria de Boussinesq. Lembre-se que as tensões se dissipam tridimensionalmente, diminuindo com a profundidade.

Flashcard: Geotecnia: Critério de Limite (Acréscimo de Carga)
Frente: Qual o critério técnico usual para delimitar a profundidade do bulbo de tensões?
Verso:
Considera-se a profundidade onde o acréscimo de tensão no solo ($\Delta \sigma$) atinge <destaque>10% da carga total</destaque> aplicada pela fundação ($\sigma_0$).

Abaixo disso, o impacto da carga é geralmente desprezível para cálculos de recalque.
Dica de Concurso: Se houver fundações muito próximas, os bulbos se sobrepõem, e a profundidade desse limite de 10% será maior do que se a sapata estivesse isolada (Efeito de Grupo).

Flashcard: Geotecnia: Regra Prática para Sapatas
Frente: Para sapatas, qual a profundidade estimada do bulbo de tensões (limite de 10%) em relação à sua largura ($B$)?
Verso:
<resumo>A profundidade corresponde a 1,5 a 2 vezes a largura ($B$) da sapata ($1,5B$ a $2B$).</resumo>
Dica de Concurso: Em questões práticas: Se a sapata tem $2\text{ m}$ de largura, as sondagens de reconhecimento do subsolo (SPT) devem ultrapassar pelo menos $4\text{ m}$ abaixo da cota de assentamento.

Flashcard: Geotecnia: Recalques em Solos Compactos/Duros
Frente: Em solos de elevada competência, como argilas duras ou areias compactas, qual a natureza física predominante que gera os recalques?
Verso:
Os recalques decorrem essencialmente de <destaque>deformações por mudança de forma (distorção lateral)</destaque>.

Ocorrem em função da carga atuante e do módulo de elasticidade do solo.
<atencao>Observação Importante:</atencao> Diferente dos solos moles, aqui os recalques não provêm da redução de volume por expulsão de água (adensamento), mas sim da reorganização estrutural imediata das partículas.
Dica de Concurso: Associe solos granulares (areias) e argilas muito duras a "Recalque Imediato" ou "Elástico", que ocorre quase simultaneamente à aplicação da carga durante a construção.

Flashcard: Geotecnia: Características dos Solos Colapsíveis
Frente: Quais as principais características estruturais e composicionais dos solos colapsíveis (subsidientes)?
Verso:

* <destaque>Grande porosidade:</destaque> Frequentemente visível a olho nu (macroporosidade).
* <destaque>Fraca cimentação:</destaque> Frequentemente composta por calcário ou óxidos ferrosos.
* <destaque>Versatilidade:</destaque> Podem ocorrer tanto em solos arenosos quanto argilosos (ex: solos porosos do Planalto Central).
Dica de Concurso: Em provas da Petrobras, solos do tipo "porosos vermelhos" são exemplos clássicos regionais de solos sujeitos ao colapso.

Flashcard: Geotecnia: Mecanismo de Colapso
Frente: O que causa o colapso repentino das fundações em solos subsidientes, segundo a prática da engenharia?
Verso:

<atencao>Gatilho Principal: SATURAÇÃO.</atencao>
O contato com a água dissolve a fraca cimentação entre os grãos.

* **Fatores:** Pode ser desencadeado por mudança na umidade (vazamentos, chuvas ou subida do nível freático) **sem necessidade** de aumento de carga externa.
* **Erosão interna (Piping):** Muitas vezes associado ao transporte de finos pela percolação de água.
Dica de Concurso: A pegadinha clássica é afirmar que o colapso só ocorre com o aumento da carga. Falso! Ele ocorre pelo aumento da umidade sob uma tensão já existente constante.

Flashcard: Geotecnia: Definição Normativa de Solo Colapsível (NBR 6122)
Frente: Qual a definição técnica de solo colapsível estabelecida pela NBR 6122?
Verso:
<resumo>"Solos que apresentam brusca redução de volume quando submetidos a acréscimos de umidade, sob a ação de carga externa."</resumo>
Dica de Concurso: Decore a palavra-chave "brusca redução de volume". Isso os diferencia do adensamento tradicional, que é um processo lento ao longo do tempo.

Flashcard: Geotecnia: Recalque Uniforme (Definição e Danos)
Frente: O que caracteriza o recalque uniforme e quais são as consequências típicas para a edificação?
Verso:

* **Definição:** O solo apresenta uma deformação homogênea sob toda a estrutura.
* **Danos:** Se excessivo, causa prejuízos ao <destaque>conforto e funcionalidade</destaque> (tubulações quebrando, degraus em acessos).
* **Impacto Estrutural:** Geralmente <destaque>não traz danos estruturais</destaque>, pois a estrutura desce como um corpo rígido, sem gerar tensões internas de cisalhamento.
Dica de Concurso: Recalque uniforme não fissura a superestrutura. Se a questão falar de trincas a 45 graus, ela está falando do recalque diferencial.

Flashcard: Geotecnia: Recalque Diferencial (Definição e Danos)
Frente: O que caracteriza o recalque diferencial e quais são as suas possíveis consequências para a edificação?
Verso:

* **Característica:** Diferentes pontos da fundação recalcam valores distintos ($\delta \neq 0$).
* **Sinais:** Fissuras inclinadas (geralmente a $45^{\circ}$) em paredes e dificuldades em fechar portas/janelas.
<atencao>Impactos Estruturais:</atencao> Pode levar à **ruína parcial ou total** por gerar esforços adicionais (momentos fletores e cortantes) não previstos originalmente em vigas e pilares.
Dica de Concurso: É o principal inimigo das estruturas hiperestáticas. Quanto mais rígida e hiperestática a estrutura, maior o esforço gerado pelo recalque diferencial.

Flashcard: Geotecnia: Vantagens do Radier contra Recalques
Frente: Por que o radier é considerado uma fundação superficial eficiente para reduzir recalques diferenciais?
Verso:

* **Distribuição de Carga:** Agrupa os pilares em uma única laje, <destaque>uniformizando a pressão</destaque> no solo.
* **Rigidez:** A grande rigidez à flexão da placa "obriga" os pontos a descerem de forma mais conjunta, minimizando o "degrau" entre pilares vizinhos.
Dica de Concurso: O radier não elimina o recalque absoluto (a estrutura inteira pode descer), mas é excelente para mitigar o diferencial.

Flashcard: Monitoramento de Recalques: Critérios de Obrigatoriedade (NBR 6122)
Frente: Quais são as 4 condições gerais estabelecidas pela NBR 6122 que tornam obrigatório o monitoramento de recalques nas estruturas?
Verso:
<atencao>O acompanhamento é obrigatório se ocorrer PELO MENOS UM dos itens:</atencao>
<resumo>

1. Altura: Mais de $55\text{ m}$ do térreo.
2. Esbeltez: $\frac{\text{Altura}}{\text{Largura}} > 4$.
3. Inovação: Fundações não convencionais.
4. Cargas: Carga móvel significativa.

</resumo>
Dica de Concurso: Para memorizar rápido na hora da prova: "55 de altura, 4 de esbeltez, Silos (cargas móveis) e Inovação".

Flashcard: Geotecnia: Equipamentos para Monitoramento de Recalques
Frente: Considere os itens: I. Nível de Terzaghi II. Nível ótico III. Nível eletrônico IV. Subsidência. Quais são equipamentos de controle?
Verso:
Apenas os itens **I, II e III**.

* **Nível de Terzaghi:** Vasos comunicantes para locais sem visada.
* **Nível Ótico/Eletrônico:** Leitura de mira com precisão milimétrica.

<atencao>Cuidado:</atencao> Subsidência é o **fenômeno** físico (rebaixamento do terreno), não o aparelho de medição.
Dica de Concurso: Piezômetro mede poropressão de água; Extensômetro mede deformação em profundidade; Inclinômetro mede deslocamento horizontal. Para recalque vertical, foque nos "Níveis".

Flashcard: Geotecnia: Atrito Negativo em Estacas
Frente: Analise as afirmações: I. Solo recalca menos que a estaca. II. Independe do lençol freático. III. É função do adensamento próprio. IV. Ocorre por amolgamento. Quais estão corretas?
Verso:
Estão corretas apenas a **III e IV**.

<atencao>Análise dos Erros:</atencao>

* **Erro da I:** No atrito negativo, o solo recalca **MAIS** que a estaca, "puxando-a" para baixo como uma carga adicional.
* **Erro da II:** O rebaixamento do lençol freático é uma das **maiores causas** de atrito negativo, pois o solo perde empuxo, aumenta a tensão efetiva e adensa.
Dica de Concurso: Atrito negativo age como "Carga" e não como "Resistência". Reduz a capacidade de carga útil da estaca.

Flashcard: Geotecnia: Estabilização de Solos com Cal
Frente: Como a adição de cal atua na estabilização de solos expansivos e colapsíveis?
Verso:
Atua através de dois mecanismos físico-químicos principais:

1. <destaque>Troca Catiônica:</destaque> Reduz a espessura da camada de água adsorvida em volta das partículas de argila (reduz o potencial de expansão).
2. <destaque>Reação Pozolânica:</destaque> Cria uma "cimentação" duradoura entre os grãos, aumentando a resistência e travando a estrutura contra o colapso.
Dica de Concurso: Regra de bolso para aditivos: Cal é excelente para solos plásticos/finos (**argilosos**). Para solos granulares (**areias**), prefere-se o cimento.

Flashcard: Geotecnia: Parâmetros Geométricos de Recalque
Frente: Qual a diferença entre Recalque Absoluto ($s$), Recalque Diferencial ($\delta$) e Distorção Angular ($\beta$)?
Verso:

<resumo>

* **Absoluto ($s$):** Descida isolada de um ponto.
* **Diferencial ($\delta$):** $\delta = s_1 - s_2$
* **Distorção ($\beta$):** $\beta = \frac{\delta}{L}$
</resumo>
* Onde $L$ é a distância horizontal entre os pontos de apoio. A Distorção Angular ($\beta$) é o parâmetro mais crítico e o principal causador de fissuras nas alvenarias.
Dica de Concurso: A NBR 6122 define limites máximos aceitáveis para a distorção angular ($\beta$) dependendo do tipo de estrutura, variando geralmente de $\frac{1}{500}$ a $\frac{1}{300}$.

Flashcard: Geotecnia: Parâmetros Adicionais (Deflexão e Desaprumo)
Frente: Defina brevemente: Deflexão Relativa ($\Delta$) e Desaprumo ($\omega$).
Verso:

* **Deflexão Relativa ($\Delta$):** Deslocamento máximo de um ponto em relação a uma reta imaginária que une outros dois pontos da fundação. Mede a <destaque>"curvatura"</destaque> da estrutura.
* **Desaprumo ($\omega$):** Rotação da estrutura como um corpo rígido. O prédio inclina <destaque>como um todo</destaque>, como a famosa Torre de Pisa, sem necessariamente fissurar internamente.
Dica de Concurso: Se a questão falar de "rotação de corpo rígido", a resposta direta é Desaprumo.

Flashcard: Geotecnia: Classificação de Fundações Profundas
Frente: Quais são os dois critérios numéricos da NBR 6122 para que uma fundação seja classificada como profunda?
Verso:
<atencao>Uma fundação é profunda apenas quando atende a AMBOS os critérios simultaneamente:</atencao>

<resumo>

1. Geométrico: $D &gt; 8B$
2. Mínimo Absoluto: Profundidade $\ge 3\text{ metros}$
</resumo>

* Onde $D$ é a profundidade de assentamento e $B$ é a menor dimensão em planta.
Dica de Concurso: É muito comum bancas colocarem que a profundidade mínima é de 2 metros ou esquecerem a regra do $8B$. Valores de $D &lt; 8B$ em elementos profundos exigem justificativa técnica formal no projeto.

Flashcard: Geotecnia: Classificação de Fundações Superficiais (Rasas)
Frente: Quando uma fundação é considerada superficial em relação à sua geometria de apoio?
Verso:
Quando a profundidade de assentamento ($D$) é **inferior a 2 vezes** a menor dimensão em planta ($B$).

<resumo>

$$D < 2B$$

</resumo>
<destaque>Referência:</destaque> Em caso de base com perímetros variáveis (poligonais complexos), utiliza-se sempre a menor profundidade e a menor dimensão como cotas de referência para o cálculo.
Dica de Concurso: Exemplos clássicos de fundações superficiais: Sapatas (isoladas, corridas, associadas), Blocos não armados e Radiers.

Flashcard: Geotecnia: Combinação de Tipos de Fundações
Frente: Por que a NBR 6122 não recomenda misturar fundações superficiais e profundas em um mesmo bloco ou edifício?
Verso:
Devido à drástica diferença de <destaque>comportamento de deformação e rigidez</destaque>.

Fundações superficiais e profundas possuem mecanismos de transferência de carga e módulos de reação (molas) muito distintos.
<atencao>Risco Principal:</atencao> Essa mistura gera **recalques diferenciais acentuados**, que podem causar trincas estruturais severas ou até o colapso do elemento de transição.
Dica de Concurso: A NBR 6122 permite a mistura apenas em casos excepcionais (ex: ampliações), desde que rigorosamente justificado e com a análise explícita da interação solo-estrutura.

Flashcard: Geotecnia: Definição e Rigidez do Radier
Frente: O que define tecnicamente um Radier e qual a porcentagem mínima de carga que ele deve distribuir?
Verso:
É um elemento de fundação superficial de grande área que abrange todos (ou a maioria) dos pilares da estrutura, assemelhando-se a uma laje contínua.

* **Critério Normativo de Carga:** Deve ter rigidez suficiente para receber e distribuir <destaque>mais do que 70%</destaque> das cargas totais da estrutura.
* **Materiais:** Pode ser executado em concreto armado, protendido ou concreto reforçado com fibras.
Dica de Concurso: Fique de olho na porcentagem de 70%. Se uma sapata abrange vários pilares mas representa menos de 70% da carga total, ela é apenas uma "Sapata Associada", não um Radier.

Flashcard: Geotecnia: Radier Nervurado
Frente: Qual o objetivo técnico de aplicar uma malha de nervuras no radier (Radier Nervurado)?
Verso:
O objetivo estrutural principal é <destaque>aumentar a rigidez à flexão</destaque> da fundação sem aumentar excessivamente o volume total de concreto.

As nervuras aumentam significativamente o momento de inércia da seção.
**Vantagem Econômica:** Permite resistir a esforços cortantes e momentos maiores com uma espessura de laje menor nas áreas internas entre nervuras, reduzindo custos e peso próprio da fundação.
Dica de Concurso: O radier nervurado atua de forma muito semelhante a uma laje nervurada de superestrutura, mas invertida (recebendo a carga uniformemente distribuída do solo de baixo para cima).

Flashcard: Geotecnia: Alívio de Carga e Viga de Equilíbrio
Frente: No dimensionamento de uma viga de equilíbrio (viga alavanca), qual a margem de segurança para o alívio de carga no pilar interno?
Verso:
Adota-se um critério conservador estabelecido em norma: considera-se o alívio atuando com apenas <destaque>50% do seu valor calculado</destaque>.

<atencao>Caso Crítico:</atencao> Se o cálculo indicar que o alívio provocado pela alavanca anula toda a compressão do pilar interno (tendência a tracionar), deve-se considerar, para fins de dimensionamento seguro da fundação, **50% da compressão inicial** (aquela sem o efeito da viga).
Dica de Concurso: Viga de equilíbrio é a solução clássica para pilares de divisa onde a sapata não pode ultrapassar o limite do terreno, transferindo o momento gerado pela excentricidade para um pilar interno.

Flashcard: Geotecnia: Sapatas Rígidas vs. Flexíveis
Frente: Qual a condição (fórmula) para que uma sapata seja classificada como rígida?
Verso:
A sapata é rígida se sua altura ($h$) for maior ou igual à terça parte da maior projeção da base em relação às faces do pilar ($A, a_p$ e $B, b_p$):

<resumo>

$$h \ge \frac{A - a_p}{3} \quad \text{e} \quad h \ge \frac{B - b_p}{3}$$

</resumo>

* **Comportamento:** Sapatas rígidas praticamente não sofrem flexão (não empenam); a distribuição das tensões de contato no solo é considerada linear ou uniforme plana.
Dica de Concurso: Sapatas flexíveis (onde o $h$ não atende à fórmula) sofrem deformação significativa e as tensões no solo concentram-se mais na região sob o pilar.

Flashcard: Geotecnia: Cargas Excêntricas e Área Comprimida
Frente: Em fundações superficiais submetidas a momentos, qual o limite mínimo de área comprimida exigido pela NBR 6122?
Verso:
A norma exige que a área efetivamente comprimida da base da fundação seja de, no mínimo, <atencao>2/3 da área total</atencao>.

Isso evita o descolamento excessivo (fresta) entre a base da sapata e o solo, garantindo a estabilidade global e a segurança contra o tombamento da estrutura.
Dica de Concurso: Isso significa que a resultante das forças deve cair dentro ou muito próxima do "núcleo central de inércia" da seção da base. Excentricidades enormes são proibidas por norma.

Flashcard: Geotecnia: Dimensões Mínimas de Sapatas e Blocos
Frente: Quais as dimensões horizontais mínimas para sapatas/blocos e a espessura mínima para blocos (NBR 6118 / NBR 6122)?
Verso:
<resumo>

* Dimensão Horizontal (Largura/Comprimento): Mínimo de $60\text{ cm}$.
* Espessura Média de Blocos: Mínimo de $20\text{ cm}$.

</resumo>
Esses valores garantem facilidade de escavação, armação (no caso de sapatas) e concretagem adequada.
Dica de Concurso: Cuidado para não confundir com a dimensão mínima de pilares ($19\text{ cm}$ ou excepcionalmente $14\text{ cm}$ na NBR 6118). Para as bases (fundações), o número mágico é $60\text{ cm}$.

Flashcard: Geotecnia: Fundações em Divisas (Profundidade)
Frente: Qual a profundidade mínima de assentamento para fundações em divisas e quais as exceções?
Verso:
A profundidade mínima obrigatória é de <destaque>$1,5\text{ m}$</destaque>.

**Exceções permitidas:**

1. Assentamento direto sobre extrato de **rocha**.
2. Obras de pequeno porte onde a maioria das sapatas/blocos tenha dimensões em planta menores que **$1,0\text{ m}$**.
Dica de Concurso: Essa exigência de $1,5\text{ m}$ visa prevenir que escavações futuras no terreno vizinho descalcem (tirem o apoio) da sua fundação periférica.

Flashcard: Geotecnia: Fundações em Cotas Diferentes
Frente: Quais os ângulos mínimos da reta de maior declive (com a vertical) para fundações vizinhas em níveis diferentes?
Verso:

Para evitar a interferência dos bulbos de tensões da sapata superior na inferior, a reta que liga as bordas deve respeitar os ângulos (em relação à vertical):

<resumo>

* Solos pouco resistentes: $\ge 60^\circ$
* Solos resistentes: $\ge 45^\circ$
* Rochas: $\ge 30^\circ$
</resumo>
Dica de Concurso: Quanto PIOR o solo (menos resistente), MAIS ABERTO tem que ser o ângulo (mais longe a sapata superior deve ficar da inferior para não carregar a vizinha).

Flashcard: Geotecnia: Escavação Mecanizada e Cota de Assentamento
Frente: Qual a distância de segurança para interromper o uso de maquinário acima da cota de fundação superficial?
Verso:
O uso de retroescavadeiras e maquinário pesado deve ser encerrado a, no mínimo, <atencao>$30\text{ cm}$ acima</atencao> da cota de assentamento final do projeto.

O restante (aperto final) deve ser removido **manualmente** para evitar a desestruturação mecânica (amolgamento) e o amolecimento indesejado do solo que servirá de apoio direto.
Dica de Concurso: Esse procedimento garante que a superfície de apoio da sapata mantenha suas características naturais de resistência (NT) avaliadas no laudo de sondagem.

Flashcard: Geotecnia: Inclinação das Paredes da Sapata
Frente: Qual o ângulo máximo para as paredes laterais da sapata inclinada (tronco de pirâmide) sem a necessidade de utilização de fôrmas superiores?
Verso:
O ângulo máximo de inclinação é de <destaque>30°</destaque> (em relação à horizontal/base do rodapé).

**Motivo Construtivo:** Este valor corresponde aproximadamente ao ângulo de atrito interno do concreto fresco padrão. Se for mais íngreme que isso, o concreto "escorre" durante o adensamento, sendo obrigatório o uso de contra-fôrmas (fôrmas na parte superior da rampa).
Dica de Concurso: Sapatas com muita inclinação aumentam a complexidade construtiva. O limite de 30° cai com frequência em provas de planejamento e execução de obras.

Flashcard: Geotecnia: Componentes do Recalque do Solo
Frente: O que é o Recalque do solo e quais são as suas 4 parcelas componentes?
Verso:
É o deslocamento vertical descendente da superfície do terreno devido ao acréscimo de tensões.

<resumo>As 4 parcelas são:</resumo>

1. **Imediato:** Ocorre no instante da carga por distorção elástica (predomina em areias).
2. **Escoamento Lateral:** Fuga lateral de material sob a carga (ocorre em areias fofas e solos muito moles).
3. **Primário (Adensamento):** Redução de volume pela expulsão lenta da água dos vazios (típico de argilas saturadas).
4. **Secundário (Secular):** Reajuste viscoso das partículas (rastejamento) após a dissipação da poropressão (típico de solos altamente orgânicos).
Dica de Concurso: Para argilas moles saturadas, o Recalque Primário é disparado a maior componente, levando anos ou décadas para estabilizar.

Flashcard: Geotecnia: Recalque Sapata vs. Placa (Argilas)
Frente: Qual a relação de recalque entre uma sapata ($\rho_s$) e uma placa de ensaio ($\rho_p$) em solos coesivos (argilosos)?
Verso:
Em argilas, o recalque é considerado diretamente proporcional à largura da base ($B$):

<resumo>

$$\frac{\rho_s}{\rho_p} = \frac{B_s}{B_p}$$

</resumo>
<atencao>Comportamento Inverso nas Areias:</atencao> Em areias, a relação empírica de Terzaghi e Peck mostra que o aumento da largura não aumenta o recalque na mesma proporção direta (a curva de recalque "achata" para larguras maiores).
Dica de Concurso: Isso significa que, em argilas, extrapolar o resultado de uma Prova de Carga sobre Placa (pequena) para uma Sapata Real (grande) gera recalques linearmente MUITO maiores.

Flashcard: Geotecnia: Ensaio Edométrico
Frente: Qual a finalidade principal do ensaio edométrico e o que ele permite estimar?
Verso:

O ensaio (também chamado de ensaio de adensamento) visa obter os parâmetros de <destaque>compressibilidade</destaque> ($C_c$, $C_s$) e os parâmetros de <destaque>adensamento no tempo</destaque> ($C_v$).

* **Utilidade Prática:** Estimativa da magnitude final do recalque total primário (quanto vai descer) e, principalmente, da **velocidade** (em quanto tempo) com que esse recalque vai ocorrer na vida real da obra.
Dica de Concurso: O Ensaio Edométrico impede a deformação lateral do corpo de prova. O solo é confinado em um anel metálico e deformado apenas na direção vertical unidimensionalmente.

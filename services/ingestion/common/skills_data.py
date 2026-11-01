"""Tagging vocabulary for every row in the `skills` table (db/postgres/schema.sql).

`description` is embedded once and compared against signal embeddings; keep it
a short, concrete sentence about the work, not the tool's marketing line.
`keywords` are regexes matched case-insensitively against title + raw_text;
any match tags the skill with KEYWORD_CONFIDENCE. Prefer specific terms over
words with an everyday meaning ("react", "go", "embedded") unless qualified.

A skill added to the table needs an entry here, or it is never tagged.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillInfo:
    description: str
    keywords: tuple[str, ...]


SKILLS: dict[str, SkillInfo] = {
    "javascript": SkillInfo(
        "Writing JavaScript for the browser or Node.js",
        (r"\bjavascript\b", r"\bnode\.?js\b", r"\bnpm\b", r"\becmascript\b", r"(?<!\.)\bjs\b"),
    ),
    "typescript": SkillInfo(
        "Writing statically typed TypeScript code",
        (r"\btypescript\b", r"\btsconfig\b", r"\.tsx?\b", r"\btype definitions\b"),
    ),
    "python": SkillInfo(
        "Writing Python scripts, libraries and backends",
        (
            r"\bpython\d?\b",
            r"\bpypi\b",
            r"\bpip install\b",
            r"\bdjango\b",
            r"\bflask\b",
            r"\bfastapi\b",
            r"\bpandas\b",
            r"\bnumpy\b",
            r"\.py\b",
        ),
    ),
    "react": SkillInfo(
        "Building web UIs with React components",
        (
            r"\breact(?:\.js|js)\b",
            r"\breact[ -](?:app|hooks?|components?|router|query|dom|context)\b",
            r"\buse(?:State|Effect|Memo|Callback|Ref)\b",
            r"\bjsx\b",
        ),
    ),
    "nextjs": SkillInfo(
        "Building full-stack web apps with Next.js",
        (r"\bnext\.?js\b", r"\bapp router\b", r"\bgetServerSideProps\b", r"\bserver components?\b"),
    ),
    "machine-learning": SkillInfo(
        "Training and evaluating machine learning models",
        (
            r"\bmachine[ -]learning\b",
            r"\bdeep learning\b",
            r"\bneural (?:network|net)s?\b",
            r"\bpytorch\b",
            r"\btensorflow\b",
            r"\bscikit-learn\b",
            r"\bsklearn\b",
            r"\bfine-?tun(?:e|ed|ing)\b",
            r"\btraining data\b",
        ),
    ),
    "computer-vision": SkillInfo(
        "Analyzing images and video with computer vision models",
        (
            r"\bcomputer vision\b",
            r"\bimage (?:classification|segmentation|recognition)\b",
            r"\bobject detection\b",
            r"\bopencv\b",
            r"\byolo(?:v\d+)?\b",
            r"\bocr\b",
        ),
    ),
    "nlp": SkillInfo(
        "Processing and understanding natural language text",
        (
            r"\bnatural language processing\b",
            r"\bnlp\b",
            r"\bnamed entit(?:y|ies)\b",
            r"\bsentiment analysis\b",
            r"\btext classification\b",
            r"\btokeni[sz](?:er|ation)\b",
            r"\bspacy\b",
        ),
    ),
    "postgresql": SkillInfo(
        "Designing schemas and writing SQL for PostgreSQL databases",
        (r"\bpostgres(?:ql)?\b", r"\bpsql\b", r"\bpostgis\b", r"\bsupabase\b"),
    ),
    "neo4j": SkillInfo(
        "Modeling and querying graph databases like Neo4j",
        (r"\bneo4j\b", r"\bcypher\b", r"\bgraph databases?\b", r"\bknowledge graphs?\b"),
    ),
    "vector-search": SkillInfo(
        "Semantic search over embeddings with a vector database",
        (
            r"\bvector (?:search|databases?|db|stores?|index(?:es)?)\b",
            r"\bembeddings?\b",
            r"\bpgvector\b",
            r"\bfaiss\b",
            r"\bpinecone\b",
            r"\bqdrant\b",
            r"\bweaviate\b",
            r"\bmilvus\b",
            r"\bsemantic search\b",
            r"\bsimilarity search\b",
            r"\bnearest[ -]neighbou?rs?\b",
        ),
    ),
    "ui-design": SkillInfo(
        "Designing user interfaces and user experience",
        (
            r"\bui\s*/\s*ux\b",
            r"\bux\b",
            r"\bui design\b",
            r"\buser interface\b",
            r"\buser experience\b",
            r"\bfigma\b",
            r"\bwireframes?\b",
            r"\bdesign system\b",
        ),
    ),
    "mobile": SkillInfo(
        "Building native or cross-platform mobile apps",
        (
            r"\bandroid\b",
            r"\bios\b",
            r"\breact native\b",
            r"\bflutter\b",
            r"\bswift(?:ui)?\b",
            r"\bkotlin\b",
            r"\bmobile apps?\b",
        ),
    ),
    "devops": SkillInfo(
        "Deploying and operating services with CI/CD and containers",
        (
            r"\bdevops\b",
            r"\bdocker(?:file)?\b",
            r"\bkubernetes\b",
            r"\bk8s\b",
            r"\bci\s*/\s*cd\b",
            r"\bterraform\b",
            r"\bhelm\b",
            r"\bansible\b",
            r"\bgithub actions\b",
        ),
    ),
    "rust": SkillInfo(
        "Writing systems software in Rust",
        (r"\brust(?:lang)?\b", r"\brustc\b", r"\bcrates\.io\b", r"\bcargo\.toml\b"),
    ),
    "go": SkillInfo(
        "Writing backend services in Go",
        (r"\bgolang\b", r"\bgoroutines?\b", r"\bgo\.mod\b", r"\bgo (?:modules?|programs?|services?)\b"),
    ),
    "data-engineering": SkillInfo(
        "Building data pipelines, ETL and warehouses",
        (
            r"\bdata engineering\b",
            r"\bdata pipelines?\b",
            r"\betl\b",
            r"\bairflow\b",
            r"\bapache spark\b",
            r"\bpyspark\b",
            r"\bkafka\b",
            r"\bdbt\b",
            r"\bdata warehouses?\b",
            r"\bsnowflake\b",
            r"\bbigquery\b",
        ),
    ),
    "geospatial": SkillInfo(
        "Working with maps, GIS and location data",
        (
            r"\bgeospatial\b",
            r"\bgis\b",
            r"\bopenstreetmap\b",
            r"\bpostgis\b",
            r"\bgdal\b",
            r"\bgeojson\b",
            r"\bmapbox\b",
            r"\bleaflet\b",
            r"\bsatellite imagery\b",
            r"\bremote sensing\b",
        ),
    ),
    "iot": SkillInfo(
        "Building connected hardware with sensors and microcontrollers",
        (
            r"\biot\b",
            r"\binternet of things\b",
            r"\barduino\b",
            r"\braspberry pi\b",
            r"\besp32\b",
            r"\bmqtt\b",
            r"\bmicrocontrollers?\b",
            r"\bembedded (?:systems?|devices?|firmware)\b",
        ),
    ),
    "llm": SkillInfo(
        "Building applications on large language models",
        (
            r"\bllms?\b",
            r"\blarge language models?\b",
            r"\bgpt-?\d",
            r"\bchatgpt\b",
            r"\bopenai\b",
            r"\banthropic\b",
            r"\bllama\b",
            r"\blangchain\b",
            r"\bretrieval[ -]augmented\b",
            r"\brag\b",
            r"\bprompt engineering\b",
        ),
    ),
}

import json

from lenskit.pipeline import Pipeline
from lenskit.pipeline.components import AutoConfig
from lenskit.pipeline.nodes import ComponentNode


class Prefixer(AutoConfig):
    prefix: str

    def __init__(self, prefix: str = "hello"):
        self.prefix = prefix

    def __call__(self, msg: str):
        return self.prefix + msg


def test_auto_config_roundtrip():
    comp = Prefixer("FOOBIE BLETCH")

    cfg = comp.get_config()
    assert "prefix" in cfg

    c2 = Prefixer.from_config(cfg)
    assert c2 is not comp
    assert c2.prefix == comp.prefix


def test_pipeline_config():
    comp = Prefixer("scroll named ")

    pipe = Pipeline()
    msg = pipe.create_input("msg", str)
    pipe.add_component("prefix", comp, msg=msg)

    assert pipe.run(msg="FOOBIE BLETCH") == "scroll named FOOBIE BLETCH"

    config = pipe.component_configs()
    print(json.dumps(config, indent=2))

    assert "prefix" in config
    assert config["prefix"]["prefix"] == "scroll named "


def test_pipeline_clone():
    comp = Prefixer("scroll named ")

    pipe = Pipeline()
    msg = pipe.create_input("msg", str)
    pipe.add_component("prefix", comp, msg=msg)

    assert pipe.run(msg="FOOBIE BLETCH") == "scroll named FOOBIE BLETCH"

    p2 = pipe.clone()
    n2 = p2.node("prefix")
    assert isinstance(n2, ComponentNode)
    assert isinstance(n2.component, Prefixer)
    assert n2.component is not comp
    assert n2.component.prefix == comp.prefix

    assert p2.run(msg="HACKEM MUCHE") == "scroll named HACKEM MUCHE"

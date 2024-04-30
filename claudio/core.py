# AUTOGENERATED! DO NOT EDIT! File to edit: ../00_core.ipynb.

# %% auto 0
__all__ = ['empty', 'models', 'g', 'tags', 'find_block', 'contents', 'usage', 'mk_msgs', 'Client', 'get_schema', 'call_func',
           'mk_toolres', 'Chat', 'img_msg', 'text_msg', 'mk_msg', 'xt', 'hl_md', 'to_xml', 'json_to_xml']

# %% ../00_core.ipynb 6
import inspect, typing, mimetypes, base64, json, xml.etree.ElementTree as ET
from collections import abc
try: from IPython import display
except: display=None

from anthropic import Anthropic
from anthropic.types import Usage, TextBlock, Message
from anthropic.types.beta.tools import ToolsBetaMessage, tool_use_block

from fastcore.docments import docments
from fastcore.utils import *

# %% ../00_core.ipynb 8
empty = inspect.Parameter.empty

# %% ../00_core.ipynb 10
models = 'claude-3-opus-20240229','claude-3-sonnet-20240229','claude-3-haiku-20240307'

# %% ../00_core.ipynb 22
def find_block(r:abc.Mapping, # The message to look in
               blk_type:type=TextBlock  # The type of block to find
              ):
    "Find the first block of type `blk_type` in `r.content`."
    return first(o for o in r.content if isinstance(o,blk_type))

# %% ../00_core.ipynb 25
def contents(r):
    "Helper to get the contents from Claude response `r`."
    blk = find_block(r)
    if not blk: blk = r.content[0]
    return blk.text.strip() if hasattr(blk,'text') else blk

# %% ../00_core.ipynb 28
@patch
def _repr_markdown_(self:(ToolsBetaMessage,Message)):
    det = '\n- '.join(f'{k}: {v}' for k,v in self.dict().items())
    return f"""{contents(self)}

<details>

- {det}

</details>"""

# %% ../00_core.ipynb 33
def usage(inp=0, # Number of input tokens
          out=0  # Number of output tokens
         ):
    "Slightly more concise version of `Usage`."
    return Usage(input_tokens=inp, output_tokens=out)

# %% ../00_core.ipynb 36
@patch(as_prop=True)
def total(self:Usage): return self.input_tokens+self.output_tokens

# %% ../00_core.ipynb 39
@patch
def __repr__(self:Usage): return f'In: {self.input_tokens}; Out: {self.output_tokens}; Total: {self.total}'

# %% ../00_core.ipynb 42
@patch
def __add__(self:Usage, b):
    "Add together each of `input_tokens` and `output_tokens`"
    return usage(self.input_tokens+b.input_tokens, self.output_tokens+b.output_tokens)

# %% ../00_core.ipynb 52
def mk_msgs(msgs:list, **kw):
    "Helper to set 'assistant' role on alternate messages."
    if isinstance(msgs,str): msgs=[msgs]
    return [mk_msg(o, ('user','assistant')[i%2], **kw) for i,o in enumerate(msgs)]

# %% ../00_core.ipynb 59
class Client:
    def __init__(self, model, cli=None):
        "Basic Anthropic messages client."
        self.model,self.use = model,Usage(input_tokens=0,output_tokens=0)
        self.c = (cli or Anthropic())

# %% ../00_core.ipynb 62
@patch
def _r(self:Client, r:ToolsBetaMessage):
    "Store the result of the message and accrue total usage."
    self.result = r
    self.use += r.usage
    return r

# %% ../00_core.ipynb 65
@patch
def __call__(self:Client,
             msgs:list, # List of messages in the dialog
             sp='', # The system prompt
             temp=0, # Temperature
             maxtok=4096, # Maximum tokens
             stop:Optional[list[str]]=None, # Stop sequences
             **kw):
    "Make a call to Claude without streaming."
    r = self.c.beta.tools.messages.create(
        model=self.model, messages=mk_msgs(msgs), max_tokens=maxtok, system=sp, temperature=temp, stop_sequences=stop, **kw)
    return self._r(r)

# %% ../00_core.ipynb 69
@patch
def stream(self:Client,
           msgs:list, # List of messages in the dialog
           sp='', # The system prompt
           temp=0, # Temperature
           maxtok=4096, # Maximum tokens
           stop:Optional[list[str]]=None, # Stop sequences
           **kw):
    "Make a call to Claude, streaming the result."
    with self.c.messages.stream(model=self.model, messages=mk_msgs(msgs), max_tokens=maxtok,
                                system=sp, temperature=temp, stop_sequences=stop, **kw) as s:
        yield from s.text_stream
        return self._r(s.get_final_message())

# %% ../00_core.ipynb 80
def _types(t:type)->tuple[str,Optional[str]]:
    "Tuple of json schema type name and (if appropriate) array item name."
    tmap = {int:"integer", float:"number", str:"string", bool:"boolean", list:"array", dict:"object"}
    if getattr(t, '__origin__', None) in  (list,tuple): return "array", tmap.get(t.__args__[0], "object")
    else: return tmap.get(t, "object"), None

# %% ../00_core.ipynb 83
def _param(name, info):
    "json schema parameter given `name` and `info` from docments full dict."
    paramt,itemt = _types(info.anno)
    pschema = dict(type=paramt, description=info.docment)
    if itemt: pschema["items"] = {"type": itemt}
    if info.default is not empty: pschema["default"] = info.default
    return pschema

# %% ../00_core.ipynb 86
def get_schema(f:callable)->dict:
    "Convert function `f` into a JSON schema `dict` for tool use."
    d = docments(f, full=True)
    ret = d.pop('return')
    paramd = {
        'type': "object",
        'properties': {n:_param(n,o) for n,o in d.items()},
        'required': [n for n,o in d.items() if o.default is empty]
    }
    desc = f.__doc__
    if ret.anno is not empty: desc += f'\n\nReturns:\n- type: {_types(ret.anno)[0]}'
    if ret.docment: desc += f'\n- description: {ret.docment}'
    return dict(name=f.__name__, description=desc, input_schema=paramd)

# %% ../00_core.ipynb 97
def _mk_ns(*funcs:list[callable]) -> dict[str,callable]:
    "Create a `dict` of name to function in `funcs`, to use as a namespace"
    return {f.__name__:f for f in funcs}

# %% ../00_core.ipynb 99
def call_func(tr:abc.Mapping, # Tool use request response from Claude
              ns:Optional[abc.Mapping]=None # Namespace to search for tools, defaults to `globals()`
             ):
    "Call the function in the tool response `tr`, using namespace `ns`."
    if ns is None: ns=globals()
    if not isinstance(ns, abc.Mapping): ns = _mk_ns(*ns)
    fc = find_block(r, tool_use_block.ToolUseBlock)
    return ns[fc.name](**fc.input)

# %% ../00_core.ipynb 102
def mk_toolres(r:abc.Mapping, # Tool use request response from Claude
               res=None,  # The result of calling the tool (calculated with `call_func` by default)
               ns:Optional[abc.Mapping]=None # Namespace to search for tools
              ):
    "Create a `tool_result` message from response `r`."
    if not hasattr(r, 'content'): return r
    tool = first(o for o in r.content if isinstance(o,tool_use_block.ToolUseBlock))
    if not tool: return r
    if res is None: res = call_func(r, ns)
    tr = dict(type="tool_result", tool_use_id=tool.id, content=str(res))
    return mk_msg([tr])

# %% ../00_core.ipynb 109
class Chat:
    def __init__(self,
                 model:Optional[str]=None, # Model to use (leave empty if passing `cli`)
                 cli:Optional[Client]=None, # Client to use (leave empty if passing `model`)
                 sp='', # Optional system prompt
                 tools:Optional[list]=None): # List of tools to make available to Claude
        "Anthropic chat client."
        assert model or cli
        self.c = (cli or Client(model))
        self.h,self.sp,self.tools = [],sp,tools

# %% ../00_core.ipynb 112
def _add_prefill(prefill, r):
    "Add `prefill` to the start of response `r`, since Claude doesn't include it otherwise"
    if not prefill: return
    blk = find_block(r)
    blk.text = prefill + blk.text

# %% ../00_core.ipynb 114
@patch
def __call__(self:Chat,
             pr,  # Prompt / message
             sp='', # The system prompt
             temp=0, # Temperature
             maxtok=4096, # Maximum tokens
             stop:Optional[list[str]]=None, # Stop sequences
             ns:Optional[abc.Mapping]=None, # Namespace to search for tools, defaults to `globals()`
             prefill='', # Optional prefill to pass to Claude as start of its response
             **kw):
    if ns is None: ns=self.tools
    if isinstance(pr,str): pr = pr.strip()
    self.h.append(mk_toolres(pr, ns=ns))
    if self.tools: kw['tools'] = [get_schema(o) for o in self.tools]
    res = self.c(self.h + ([prefill.strip()] if prefill else []), sp=self.sp, temp=temp, maxtok=maxtok, stop=stop, **kw)
    _add_prefill(prefill, res)
    self.h.append(mk_msg(res, role='assistant'))
    return res

# %% ../00_core.ipynb 120
@patch
def stream(self:Chat,
           pr,  # Prompt / message
           sp='', # The system prompt
           temp=0, # Temperature
           maxtok=4096, # Maximum tokens
           stop:Optional[list[str]]=None, # Stop sequences
           prefill='', # Optional prefill to pass to Claude as start of its response
           **kw):
    "Add a prompt and get a response from the chat dialog, streaming the result"
    if isinstance(pr,str): pr = pr.strip()
    self.h.append(pr)
    if prefill: yield(prefill)
    yield from self.c.stream(self.h + ([prefill.strip()] if prefill else []), sp=self.sp, temp=temp, maxtok=maxtok, stop=stop, **kw)
    _add_prefill(prefill, self.c.result)
    self.h.append(mk_msg(self.c.result, role='assistant'))

# %% ../00_core.ipynb 134
def img_msg(data:bytes)->dict:
    "Convert image `data` into an encoded `dict`"
    img = base64.b64encode(data).decode("utf-8")
    mtype = mimetypes.guess_type(fn)[0]
    r = dict(type="base64", media_type=mtype, data=img)
    return {"type": "image", "source": r}

# %% ../00_core.ipynb 136
def text_msg(s:str)->dict:
    "Convert `s` to a text message"
    return {"type": "text", "text": s}

# %% ../00_core.ipynb 140
def _mk_content(src):
    "Create appropriate content data structure based on type of content"
    if isinstance(src,str): return text_msg(src)
    if isinstance(src,bytes): return img_msg(src)
    return src

# %% ../00_core.ipynb 143
def mk_msg(content, # A string, list, or dict containing the contents of the message
           role='user', # Must be 'user' or 'assistant'
           **kw):
    "Helper to create a `dict` appropriate for a Claude message. `kw` are added as key/value pairs to the message"
    if hasattr(content, 'content'): content,role = content.content,content.role
    if isinstance(content, abc.Mapping): content=content['content']
    if not isinstance(content, list): content=[content]
    content = [_mk_content(o) for o in content]
    return dict(role=role, content=content, **kw)

# %% ../00_core.ipynb 153
def xt(tag:str, # XML tag name
       c:Optional[list]=None, # Children
       **kw):
    "Helper to create appropriate data structure for `to_xml`."
    kw = {k.lstrip('_'):str(v) for k,v in kw.items()}
    return tag,c,kw

# %% ../00_core.ipynb 156
g = globals()
tags = 'div img h1 h2 h3 h4 h5 p hr span html'.split()
for o in tags: g[o] = partial(xt, o)

# %% ../00_core.ipynb 159
def hl_md(s, lang='xml'):
    "Syntax highlight `s` using `lang`."
    if display: return display.Markdown(f'```{lang}\n{s}\n```')
    print(s)

# %% ../00_core.ipynb 162
def to_xml(node:tuple, # XML structure in `xt` format
           hl=False # Syntax highlight response?
          ):
    "Convert `node` to an XML string."
    def mk_el(tag, cs, attrs):
        el = ET.Element(tag, attrib=attrs)
        if isinstance(cs, list): el.extend([mk_el(*o) for o in cs])
        elif cs is not None: el.text = str(cs)
        return el

    root = mk_el(*node)
    ET.indent(root)
    res = ET.tostring(root, encoding='unicode')
    return hl_md(res) if hl else res

# %% ../00_core.ipynb 165
def json_to_xml(d:dict, # JSON dictionary to convert
                rnm:str # Root name
               )->str:
    "Convert `d` to XML."
    root = ET.Element(rnm)
    def build_xml(data, parent):
        if isinstance(data, dict):
            for key, value in data.items(): build_xml(value, ET.SubElement(parent, key))
        elif isinstance(data, list):
            for item in data: build_xml(item, ET.SubElement(parent, 'item'))
        else: parent.text = str(data)
    build_xml(d, root)
    ET.indent(root)
    return ET.tostring(root, encoding='unicode')

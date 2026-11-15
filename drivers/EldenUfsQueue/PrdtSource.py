"""Extract the pinned ShengUfs page-coalescing algorithm, with explicit bounds."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
def function(text,signature):
    start=text.index(signature);at=text.index('{',start);depth=1;end=at+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
def header():
    pin=json.loads((ROOT/'upstream/source.json').read_text())
    for name,digest in pin['files'].items():
        if hashlib.sha256((ROOT/'upstream'/name).read_bytes()).hexdigest()!=digest:raise ValueError('Upstream input differs: '+name)
    text=(ROOT/'upstream/RootCommands.h').read_text()
    fn=function(text,'static unsigned hostBuildPrds (')
    fn=fn.replace('static unsigned hostBuildPrds (const void *buffer, uint64_t bytes, UfsPrd *prd)',
                  'template<class Map> static unsigned eldenUfsBuildPrds (const void *buffer, uint64_t bytes, UfsPrd *prd, Map hostDmaAddress)')
    brace=fn.index('{')+1
    fn=fn[:brace]+'''
  const bool gZeroCopy=true;
  if(!prd || bytes > UINTPTR_MAX - reinterpret_cast<uintptr_t>(buffer)) return 0;
'''+fn[brace:]
    return ('''// SPDX-License-Identifier: BSD-2-Clause-Patent
// Derived from pinned ShengUfs; see upstream/LICENSE and source.json.
#pragma once
#include <stdint.h>
namespace elden_prdt {
struct UfsPrd { uint64_t addr; uint32_t bytes; };
static constexpr unsigned kMaxPrds=64;
static constexpr uint32_t kXferMax=1U<<20,kPrdMax=256U<<10;
'''+fn+'\n}\n').encode()

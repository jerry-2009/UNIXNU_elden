"""Change only exact native_owner_data_seed_size predicates for a2GiB profile."""
import re
PATTERN=re.compile(r'(native_owner_data_seed_size\s*(?:==|!=)\s*)(UINT64_C\(536870912\)|536870912ULL)')
def patch(data):
    text=data.decode();found=list(PATTERN.finditer(text))
    if not found:return data,0
    result=PATTERN.sub(lambda m:m[1]+('UINT64_C(2147483648)' if m[2].startswith('UINT64_C') else '2147483648ULL'),text)
    reverse=re.sub(r'(native_owner_data_seed_size\s*(?:==|!=)\s*)(UINT64_C\(2147483648\)|2147483648ULL)',
        lambda m:m[1]+('UINT64_C(536870912)' if m[2].startswith('UINT64_C') else '536870912ULL'),result)
    if reverse!=text:raise ValueError('Capacity predicate replacement is not reversible')
    return result.encode(),len(found)

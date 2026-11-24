"""同一罐车计量票时间重叠的判定与合并。

规则：
- 时间窗按半开区间 [opened, closed) 比较，首尾相接（前票 closed == 后票 opened）不算重叠；
- 同车时间重叠的票用并查集归入同一重叠组；
- 有可靠重打凭据、且凭据完整覆盖整组时，整组确认为同一笔发油，只保留一票入账，
  其余票标记 MERGED_DUPLICATE，原件全部留痕可查；
- 没有可靠凭据的重叠组即使各有签收也一律留待核（OVERLAP_PENDING），
  所属罐车列为争议车，暂不出库存盈亏。
"""
from collections import defaultdict

from app.diagnostics import detail


class _Union:
    def __init__(self, members):
        self.parent = {member:member for member in members}

    def find(self, member):
        root = member
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[member] != root:
            self.parent[member], member = root, self.parent[member]
        return root

    def join(self, left, right):
        self.parent[self.find(left)] = self.find(right)


def _overlaps(left, right):
    # 半开区间：closed == 另一票 opened 时首尾相接，照常核算
    return max(left['opened'], right['opened']) < min(left['closed'], right['closed'])


def _components(weights):
    by_truck = defaultdict(list)
    for row in weights:
        if row['standard'] is not None:
            by_truck[row['truck']].append(row)
    components = []
    for truck, rows in by_truck.items():
        ordered = sorted(rows, key=lambda item:(item['ticket_record']['opened'], item['line']))
        union = _Union(item['ticket'] for item in ordered)
        for index, left in enumerate(ordered):
            for right in ordered[index+1:]:
                if right['ticket_record']['opened'] >= left['ticket_record']['closed']:
                    break
                if _overlaps(left['ticket_record'], right['ticket_record']):
                    union.join(left['ticket'], right['ticket'])
        groups = defaultdict(list)
        for item in ordered:
            groups[union.find(item['ticket'])].append(item)
        components.extend({'truck':truck,
                           'tickets':[item['ticket'] for item in group],
                           'lines':[item['line'] for item in group]}
                          for group in groups.values() if len(group) > 1)
    return components


def _evidence_book(reprint_sheet):
    """重打凭据逐条留痕；结构坏件不可靠，后续再校验指向关系。"""
    book = []
    for item in reprint_sheet['rows']:
        record = item['data']
        book.append({'reprint':record['reprint'],'truck':record['truck'],'line':item['line'],
                     'members':list(record['members']),'document':record['document'],
                     'usable':True,'fault':None})
    for item in reprint_sheet['quarantine']:
        record = item.get('data') or {}
        book.append({'reprint':record.get('reprint'),'truck':record.get('truck'),'line':item['line'],
                     'members':list(record.get('members',[])),'document':record.get('document'),
                     'usable':False,'fault':detail(item['code'])})
    return book


def detect_overlaps(weights, intake):
    """返回每张质量票的重叠角色，以及重叠组、重打凭据和争议罐车清单。"""
    components = _components(weights)
    evidence = _evidence_book(intake['sheets']['reprints'])
    indexed = {row['ticket']:row for row in weights}
    truck_of = {row['ticket']:row['truck'] for row in weights}

    for slip in evidence:
        if not slip['usable']:
            continue
        members = slip['members']
        if any(ticket not in indexed for ticket in members) or \
           any(truck_of[ticket] != slip['truck'] for ticket in members):
            slip['usable'] = False
            slip['fault'] = detail('EVIDENCE')

    groups, roles = [], {}
    disputed_trucks = set()
    for component in components:
        tickets = set(component['tickets'])
        # 可靠凭据只在不越出本组时采信；组内每票都被覆盖，且凭据把整组连成一体
        internal = [slip for slip in evidence
                    if slip['usable'] and set(slip['members']) <= tickets and len(slip['members']) > 1]
        link = _Union(component['tickets'])
        covered = set()
        for slip in internal:
            members = slip['members']
            for ticket in members[1:]:
                link.join(members[0], ticket)
            covered.update(members)
        root = link.find(component['tickets'][0])
        confirmed = bool(internal) and covered == tickets and \
            all(link.find(ticket) == root for ticket in tickets)
        ordered_ids = component['tickets']
        group = dict(component, status='CONFIRMED' if confirmed else 'PENDING',
                     keeper=ordered_ids[0] if confirmed else None,
                     merged=ordered_ids[1:] if confirmed else [],
                     evidence=sorted({slip['line'] for slip in internal}))
        if confirmed:
            roles[ordered_ids[0]] = {'component':group,'role':'KEEPER'}
            for ticket in ordered_ids[1:]:
                roles[ticket] = {'component':group,'role':'MERGED_DUPLICATE'}
        else:
            disputed_trucks.add(component['truck'])
            for ticket in ordered_ids:
                roles[ticket] = {'component':group,'role':'OVERLAP_PENDING'}
        groups.append(group)
    return {'groups':groups,'roles':roles,'evidence':evidence,
            'disputed_trucks':sorted(disputed_trucks),
            'confirmed_groups':sum(group['status']=='CONFIRMED' for group in groups),
            'pending_groups':sum(group['status']=='PENDING' for group in groups)}

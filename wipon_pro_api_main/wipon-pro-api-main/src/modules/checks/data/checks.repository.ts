import { EntityRepository, MoreThan, Repository } from 'typeorm';
import { CheckDao } from '../../../common/dao/check.dao';
import { paginate } from '../../../common/utils/common';
import { formatCheckDataToResponse } from '../../../common/helpers/dataToResponse/checks-data-to-response';

@EntityRepository(CheckDao)
export class ChecksRepository extends Repository<CheckDao> {
  async countUsersChecksForMonth(userId: number, startOfMonth: Date): Promise<number> {
    return this.count({ where: { user_id: userId, created_at: MoreThan(startOfMonth) } });
    // return await this.createQueryBuilder('checks')
    //   .where('user_id = :userId', { userId })
    //   .where('created_at > :startOfMonth', { startOfMonth })
    //   .getCount();
  }

  async getUsersUniqueChecksForMonth(userId: number, startOfMonth: Date): Promise<number> {
    return await this.query(
      'select count(*) as amount from checks where id in (select max(id) from CHECKS where user_id = $1 and created_at > $2 group by item_id)',
      [userId, startOfMonth],
    );
  }

  async countUsersChecks(userId: number): Promise<number> {
    return await this.count({ user_id: userId });
  }

  async countUsersUniqueChecks(userId: number) {
    return await this.query(
      'select count(*) as amount from checks where id in (select max(id) from CHECKS where user_id = $1 group by item_id)',
      [userId],
    );
  }

  async getUsersCheckWithItemProducts(userId: number, status: string | null, page: number, fullUrl: string) {
    const perPage = 50;

    // const newQuery = this.query(
    //   'select checks.created_at as created_at, checks.sticker_photo as sticker_photo,' +
    //     ' items.id as item_id, items.status as item_status, items.serial_number as item_serial_number,' +
    //     ' items.excise_code as item_excise_code, items.bottled_at as item_bottled_at, products.name as product_name,' +
    //     ' products.type as product_type, products.organization as organization from checks' +
    //     ' left join items on checks.item_id = items.id' +
    //     ' left join products on items.product_id = products.id' +
    //     ' where checks.user_id = $1' +
    //     ' order by checks.id DESC limit $2 offset $3',
    //   [userId, perPage, perPage * (page - 1)],
    // );

    let query = this.createQueryBuilder('checks')
      .leftJoinAndSelect('checks.item', 'item')
      .leftJoinAndSelect('item.product', 'product')
      .where('checks.user_id = :userId', { userId })
      .orderBy('checks.id', 'DESC');

    if (status !== null) {
      // query.innerJoin('item.checks', 'item').where('items.status = :status', { status });
      query = query.andWhere('item.status = :status', { status });
    }

    const [checks, count] = await query
      .take(perPage)
      .skip(perPage * (page - 1))
      .getManyAndCount();

    const data = checks.map((el) => {
      return formatCheckDataToResponse(el);
    });

    // {
    //   "created_at": "2022-09-16T10:01:59.000Z",
    //   "sticker_photo": null,
    //   "item": {
    //   "id": 117004812,
    //     "product": {
    //     "name": "\"Горный Король (Mountain King) традиционный специального наименования особый 0.5 л.",
    //       "type": "Бренди",
    //       "organization": "АО \"Винзавод \"Иссык\""
    //   },
    //   "status": "valid",
    //     "serial_number": "AA227970654",
    //     "product_code": "AA227970654",
    //     "bottled_at": "2021-06-29T18:00:00.000Z"
    // }
    // },

    return paginate(data, count, page, perPage, fullUrl);
  }
}

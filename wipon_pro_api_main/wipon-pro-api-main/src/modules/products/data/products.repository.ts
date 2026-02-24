import { EntityRepository, Repository } from 'typeorm';
import { ProductDao } from '../../../common/dao/product.dao';

@EntityRepository(ProductDao)
export class ProductsRepository extends Repository<ProductDao> {
  async findOrCreate(name: string, organization: string, type: string) {
    const product = await this.findOne({
      where: { name, organization, type },
    });
    if (!product) {
      return this.save({ name, organization, type });
    }
    return product;
  }
}

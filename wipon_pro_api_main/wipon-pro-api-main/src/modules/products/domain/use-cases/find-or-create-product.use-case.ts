import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { ProductsRepository } from '../../data/products.repository';
import { ProductDao } from '../../../../common/dao/product.dao';

@Injectable()
export class FindOrCreateProductUseCase {
  constructor(@InjectRepository(ProductsRepository) private readonly productsRepository: ProductsRepository) {}

  handle(name: string, organization: string, type: string): Promise<ProductDao> {
    return this.productsRepository.findOrCreate(name, organization, type);
  }
}

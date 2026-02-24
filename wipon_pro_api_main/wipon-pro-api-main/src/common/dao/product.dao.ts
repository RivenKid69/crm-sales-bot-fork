import { Column, Entity, OneToOne, PrimaryGeneratedColumn } from 'typeorm';
import { ItemDao } from './item.dao';

@Entity('products')
export class ProductDao {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  type: string;

  @Column()
  organization: string;

  @Column()
  name: string;

  @Column()
  is_exported: boolean;

  @OneToOne(() => ItemDao, (item) => item.product)
  item: ItemDao;
}

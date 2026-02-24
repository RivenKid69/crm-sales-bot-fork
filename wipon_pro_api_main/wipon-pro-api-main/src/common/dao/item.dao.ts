import {
  BaseEntity,
  Column,
  CreateDateColumn,
  Entity,
  JoinColumn,
  OneToMany,
  OneToOne,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { CheckDao as Check } from './check.dao';
import { ProductDao } from './product.dao';

@Entity('items')
export class ItemDao extends BaseEntity {
  static readonly ITEM_STATUS_VALID = 0;
  static readonly ITEM_STATUS_FAKE = 1;
  static readonly ITEM_STATUS_ATLAS = 2;

  @PrimaryGeneratedColumn()
  id: number;

  @Column({ name: 'product_id', nullable: true })
  product_id: number | null;

  @Column({ name: 'excise_code' })
  excise_code: string;

  @Column({ name: 'serial_number' })
  serial_number: string;

  @Column({ name: 'bottled_at' })
  bottled_at: Date;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updated_at: Date;

  @Column({
    type: 'smallint',
    default: 1,
  })
  status: number;

  @Column()
  hash: string;

  @Column()
  gtin: string;

  @OneToMany(() => Check, (check) => check.item)
  checks: Check[];

  @OneToOne(() => ProductDao, (product) => product.item, { nullable: true })
  @JoinColumn({ name: 'product_id' })
  product: ProductDao;
}

import {
  Column,
  CreateDateColumn,
  Entity,
  JoinColumn,
  ManyToOne,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { ItemDao as Item } from './item.dao';

@Entity('checks')
export class CheckDao {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  item_id: number;

  @Column()
  user_id: number;

  @Column()
  store_id: number;

  @Column({
    type: 'double precision',
  })
  latitude: number;

  @Column({
    type: 'double precision',
  })
  longitude: number;

  @Column()
  accuracy: number;

  @CreateDateColumn()
  created_at: Date;

  @UpdateDateColumn()
  updated_at: Date;

  @Column()
  sticker_photo: string;

  @Column()
  third_party: string;

  @ManyToOne(() => Item, (item) => item.checks)
  @JoinColumn({
    name: 'item_id',
  })
  item: Item;
}
